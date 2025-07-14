# recognition_server.py (Expanded Backend with Global PIN)
import os
import io
import time
import datetime
import uuid
import traceback
import pytz
from scipy.spatial import cKDTree # Keep for potential neighbor analysis later
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import torch
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
from PIL import Image
try:
    from skimage.metrics import structural_similarity as ssim
except ImportError:
    print("WARN: scikit-image not found. Install it for SSIM comparison (`pip install scikit-image`). Falling back to basic MSE.")
    ssim = None

from flask import Flask, request, jsonify, send_from_directory, g
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.utils import secure_filename
from sqlalchemy import Index

# Authentication & Security
from passlib.context import CryptContext
import jwt # PyJWT
from functools import wraps

# Face Recognition
import cv2
import numpy as np
from deepface import DeepFace
import warnings

# --- Configuration ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, 'neuralock.db')
KNOWN_FACES_PATH = os.path.join(BASE_DIR, "known_faces")
#UPLOAD_FOLDER_AVATARS = os.path.join(BASE_DIR, "uploads", "avatars")
UPLOAD_FOLDER_INTRUDER = os.path.join(BASE_DIR, "uploads", "intruder_images")
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
DEFAULT_GLOBAL_PIN = "123456" # Default if not set in DB
LOCAL_TIMEZONE = pytz.timezone('Asia/Kolkata')


#---liveness-check-configurations---
FACE_CASCADE_PATH = 'C:\\Projects\\neuralock_server\\.venv\\Lib\\site-packages\\cv2\\data\\haarcascade_frontalface_default.xml'
HEATMAP_INTERPOLATION_METHOD = 'cubic'
SIMILARITY_THRESHOLD = 0.3
DEPTH_MODEL_NAME = "depth-anything/Depth-Anything-V2-Small-hf"

# CLAHE Parameters
CLAHE_CLIP_LIMIT = 3.0
CLAHE_TILE_GRID_SIZE = (16, 16)

# Adaptive Threshold Parameters (Tune based on CLAHE output)
thresh_block_size = 31 # Larger might be better
thresh_C = 7           # Adjust
thresh_type = cv2.THRESH_BINARY_INV # Assuming dots bright after CLAHE

# Morphological Opening Parameters
morph_kernel_size = 3
morph_iterations = 1

# Blob Detector Parameters (Tune based on morphology output)
blob_params = cv2.SimpleBlobDetector_Params()
blob_params.filterByColor = True; blob_params.blobColor = 255 # White blobs
blob_params.filterByArea = True; blob_params.minArea = 20; blob_params.maxArea = 200
blob_params.filterByCircularity = True; blob_params.minCircularity = 0.7
blob_params.filterByConvexity = True; blob_params.minConvexity = 0.80
blob_params.filterByInertia = True; blob_params.minInertiaRatio = 0.5
#-------------

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = 'neuralock1234' # CHANGE THIS!
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
#app.config['UPLOAD_FOLDER_AVATARS'] = UPLOAD_FOLDER_AVATARS
app.config['UPLOAD_FOLDER_INTRUDER'] = UPLOAD_FOLDER_INTRUDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

#os.makedirs(UPLOAD_FOLDER_AVATARS, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_INTRUDER, exist_ok=True)
os.makedirs(KNOWN_FACES_PATH, exist_ok=True)

# --- Database Setup ---
db = SQLAlchemy(app)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Database Models ---
class User(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # pin_hash = db.Column(db.String(128), nullable=True) # REMOVED from User
    role = db.Column(db.String(50), nullable=False, default='Family Member')
    avatar = db.Column(db.String(200), nullable=True, default='default_avatar.png')
    date_added = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    logs = db.relationship('Log', backref='user_ref', lazy=True)
    phone = db.Column(db.String(50), nullable=True)

    def set_password(self, password):
        self.password_hash = pwd_context.hash(password)

    def check_password(self, password):
        return pwd_context.verify(password, self.password_hash)

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    type = db.Column(db.String(50), nullable=False)
    details = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=True)
    image_path = db.Column(db.String(200), nullable=True)
    __table_args__ = (Index('ix_log_timestamp', 'timestamp'), Index('ix_log_type', 'type'))

# ---> NEW Setting Model <---
class Setting(db.Model):
    key = db.Column(db.String(50), primary_key=True) # e.g., 'global_pin_hash'
    value = db.Column(db.String(200), nullable=False)


# --- Helper Functions ---
def verify_token(token):
    # ... (same as before) ...
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        return payload['sub'] # Returns user ID
    except: return None

def get_token_from_header():
    # ... (same as before) ...
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '): return auth_header.split(' ')[1]
    return None

def get_user_from_token():
    # ... (same as before) ...
    token = get_token_from_header()
    if not token: return None
    user_id = verify_token(token)
    if not user_id: return None
    return User.query.get(user_id)

# Decorator for protected routes
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        g.current_user = get_user_from_token() # Store user in Flask's 'g' object for access in route
        if g.current_user is None:
            return jsonify({"status": "error", "message": "Token is missing or invalid"}), 401
        return f(*args, **kwargs)
    return decorated

# Decorator for Admin only routes
def admin_required(f):
    @wraps(f)
    @token_required # Admin must also be logged in
    def decorated(*args, **kwargs):
        if not g.current_user or g.current_user.role != 'Admin':
             return jsonify({"status": "error", "message": "Admin privileges required"}), 403 # Forbidden
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    # ... (same as before) ...
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def trigger_deepface_reindex(user_id=None):
    # ... (same as before - delete main representations pkl file) ...
    print("INFO: Triggering DeepFace re-index...")
    try:
        pkl_path = os.path.join(KNOWN_FACES_PATH, f"representations_{DEEPFACE_MODEL_NAME.lower()}.pkl") # Use model name in path
        if os.path.exists(pkl_path):
            os.remove(pkl_path)
            print(f"INFO: Removed {pkl_path}")
    except Exception as e:
        print(f"ERROR: Could not remove DeepFace representation file: {e}")

# --- DeepFace Configuration ---
DEEPFACE_MODEL_NAME = "ArcFace"
DEEPFACE_DETECTOR_BACKEND = "retinaface"
DEEPFACE_RECOGNITION_THRESHOLD = 0.35

# ... (DeepFace model preloading remains same) ...
print("Loading DeepFace models...")
# Preload model (optional) - Comment out if causing issues on start
try:
    _ = DeepFace.represent(img_path=np.zeros((100, 100, 3)), model_name=DEEPFACE_MODEL_NAME, enforce_detection=False, detector_backend='skip')
    print(f"DeepFace model ({DEEPFACE_MODEL_NAME}) loaded.")
except Exception as e:
    print(f"Warning: Could not preload DeepFace model. Error: {e}")

# --- Authentication Routes ---
# /login remains the same (remove has_pin_set if not needed)
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'): return jsonify({"status": "error", "message": "Missing email or password"}), 400
    user = User.query.filter_by(email=data['email']).first()
    if user and user.check_password(data['password']):
        token = jwt.encode({'sub': user.id, 'iat': datetime.datetime.utcnow(), 'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)}, app.config['SECRET_KEY'], algorithm="HS256")
        user_data = {
            "id": user.id, "name": user.name, "email": user.email,
            "role": user.role,
            "avatar": user.avatar # Send the path stored in DB (e.g., known_faces/...)
        }
        return jsonify({"status": "success", "token": token, "user": user_data})
    else: return jsonify({"status": "error", "message": "Invalid credentials"}), 401

# --- API Routes (Protected) ---

@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile():
    user = get_user_from_token()
    if not user: return jsonify({"status": "error", "message": "User not found"}), 404 # Should not happen if token_required works
    user_data = {
        "id": user.id, "name": user.name, "email": user.email, "role": user.role,
        "avatar": user.avatar, # Send stored path
        "dateAdded": user.date_added.isoformat()
    }
    return jsonify({"status": "success", "user": user_data})

@app.route('/api/profile', methods=['PUT'])
@token_required
def update_profile():
    user = g.current_user # Get user from decorator context
    if not user: return jsonify({"status": "error", "message": "User not found"}), 404
    data = request.get_json()
    if not data: return jsonify({"status": "error", "message": "Missing data"}), 400

    if 'name' in data: user.name = data['name']
    if 'email' in data: user.email = data['email']
    if 'role' in data: user.role = data['role']
    if 'phone' in data: user.phone = data['phone']

    try:
        db.session.commit()
        return jsonify({"status": "success", "message": "Profile updated"})
    except Exception as e:
        db.session.rollback()
        print(f"ERROR updating profile for {user.email}: {e}")
        return jsonify({"status": "error", "message": "Database error updating profile"}), 500

@app.route('/api/profile/password', methods=['PUT'])
@token_required
def change_password():
    user = g.current_user
    data = request.get_json()
    if not data or 'current_password' not in data or 'new_password' not in data:
        return jsonify({"status": "error", "message": "Missing current or new password"}), 400

    current_pass = data['current_password']
    new_pass = data['new_password']

    if len(new_pass) < 6: # Example minimum length
         return jsonify({"status": "error", "message": "New password must be at least 6 characters"}), 400

    if not user.check_password(current_pass):
        return jsonify({"status": "error", "message": "Incorrect current password"}), 403

    try:
        user.set_password(new_pass)
        db.session.commit()
        print(f"INFO: Password updated for user {user.email}")
        return jsonify({"status": "success", "message": "Password updated successfully"})
    except Exception as e:
        db.session.rollback(); print(f"ERROR updating password: {e}")
        return jsonify({"status": "error", "message": "Database error updating password"}), 500

@app.route('/api/profile/avatar', methods=['POST'])
@token_required
def upload_profile_avatar():
    user = get_user_from_token()
    if not user: return jsonify({"status": "error", "message": "User not found"}), 404

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    if file and allowed_file(file.filename):
        try:
            # Create unique filename
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"avatar_{user.id}_{uuid.uuid4().hex[:8]}.{ext}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], filename)
            file.save(save_path)

            # Delete old avatar if it's not the default
            if user.avatar and user.avatar != 'default_avatar.png':
                old_path = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], user.avatar)
                if os.path.exists(old_path):
                    try: os.remove(old_path)
                    except Exception as e_del: print(f"WARN: Could not delete old avatar {old_path}: {e_del}")

            user.avatar = filename # Save only filename (relative path)
            db.session.commit()
            return jsonify({"status": "success", "message": "Avatar uploaded", "avatar": filename})
        except Exception as e:
            db.session.rollback()
            print(f"ERROR uploading avatar: {e}")
            return jsonify({"status": "error", "message": f"Failed to upload avatar: {e}"}), 500
    else:
        return jsonify({"status": "error", "message": "File type not allowed"}), 400


@app.route('/api/users', methods=['GET'])
@token_required
def get_users():
    # Add role check here if needed: current_user = get_user_from_token(); if current_user.role != 'Admin': return ...
    users = User.query.order_by(User.name).all()
    user_list = [{
        "id": u.id, "name": u.name, "email": u.email, "role": u.role,
        "avatar": u.avatar, "dateAdded": u.date_added.isoformat()
    } for u in users]
    return jsonify({"status": "success", "users": user_list})

@app.route('/api/users', methods=['POST'])
@token_required
def create_user():
    # Add role check here if needed
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({"status": "error", "message": "Missing required fields (name, email, password)"}), 400

    if User.query.filter_by(email=data['email']).first():
        return jsonify({"status": "error", "message": "Email already exists"}), 409

    try:
        new_user = User(
            id=str(uuid.uuid4()), # Generate ID here
            email=data['email'],
            name=data['name'],
            role=data.get('role', 'Family Member') # Default role
        )
        new_user.set_password(data['password'])
        # Handle PIN if needed: new_user.set_pin(...)
        db.session.add(new_user)

        # Create directory for known faces
        user_face_dir = os.path.join(KNOWN_FACES_PATH, new_user.id) # Use ID for folder name
        os.makedirs(user_face_dir, exist_ok=True)

        db.session.commit()

        user_data = { "id": new_user.id, "name": new_user.name, "email": new_user.email, "role": new_user.role, "avatar": new_user.avatar, "dateAdded": new_user.date_added.isoformat()}
        return jsonify({"status": "success", "user": user_data}), 201 # 201 Created status

    except Exception as e:
        db.session.rollback()
        print(f"ERROR creating user: {e}")
        return jsonify({"status": "error", "message": "Database error creating user"}), 500


@app.route('/api/users/<user_id>', methods=['DELETE'])
@token_required
def delete_user(user_id):
    # Add role check here if needed
    user = User.query.get(user_id)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    try:
        # Delete associated logs? Or anonymize them? Decide policy. For now, keep logs.
        # Delete face images directory
        user_face_dir = os.path.join(KNOWN_FACES_PATH, user.id)
        if os.path.exists(user_face_dir):
            import shutil
            shutil.rmtree(user_face_dir)
            print(f"INFO: Removed face directory {user_face_dir}")

        # Delete avatar image
        if user.avatar and user.avatar != 'default_avatar.png':
            avatar_path = os.path.join(app.config['UPLOAD_FOLDER_AVATARS'], user.avatar)
            if os.path.exists(avatar_path):
                 try: os.remove(avatar_path)
                 except Exception as e_del: print(f"WARN: Could not delete avatar {avatar_path}: {e_del}")

        db.session.delete(user)
        db.session.commit()
        trigger_deepface_reindex() # Force re-index after deleting user faces
        return jsonify({"status": "success", "message": "User deleted"})
    except Exception as e:
        db.session.rollback()
        print(f"ERROR deleting user: {e}")
        return jsonify({"status": "error", "message": "Database error deleting user"}), 500


@app.route('/api/users/<user_id>/images', methods=['GET'])
@token_required
def get_user_face_images(user_id):
    if g.current_user.role != 'Admin' and g.current_user.id != user_id: return jsonify({"status": "error", "message": "Permission denied"}), 403
    user_face_dir = os.path.join(KNOWN_FACES_PATH, user_id)
    if not os.path.isdir(user_face_dir): return jsonify({"status": "success", "images": []})
    try:
        image_files = [f for f in os.listdir(user_face_dir) if allowed_file(f)]
        # ---> Return path relative to base URL needed by client <---
        image_list = [{"filename": f, "path": f"known_faces/{user_id}/{f}"} for f in image_files]
        return jsonify({"status": "success", "images": image_list})
    except Exception as e:
        print(f"ERROR listing user images: {e}")
        return jsonify({"status": "error", "message": "Error listing images"}), 500


@app.route('/api/users/<user_id>/images', methods=['POST'])
@token_required
def upload_user_face_image(user_id):
    # Add role check if needed
    user = User.query.get(user_id)
    if not user: return jsonify({"status": "error", "message": "User not found"}), 404

    if 'file' not in request.files: return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"status": "error", "message": "No selected file"}), 400

    if file and allowed_file(file.filename):
        try:
            user_face_dir = os.path.join(KNOWN_FACES_PATH, user.id)
            os.makedirs(user_face_dir, exist_ok=True) # Ensure directory exists

            # Sanitize and create unique filename to avoid conflicts/overwrites
            base, ext = os.path.splitext(secure_filename(file.filename))
            filename = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
            save_path = os.path.join(user_face_dir, filename)
            file.save(save_path)

            trigger_deepface_reindex() # Force re-index after adding image
            return jsonify({"status": "success", "message": "Image uploaded", "filename": filename})

        except Exception as e:
            print(f"ERROR uploading user face image: {e}")
            return jsonify({"status": "error", "message": f"Failed to upload image: {e}"}), 500
    else:
        return jsonify({"status": "error", "message": "File type not allowed"}), 400


@app.route('/api/users/<user_id>/images/<filename>', methods=['DELETE'])
@token_required
def delete_user_face_image(user_id, filename):
    # Auth Check: Admin or Self
    if g.current_user.role != 'Admin' and g.current_user.id != user_id:
        return jsonify({"status": "error", "message": "Permission denied"}), 403

    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({"status": "error", "message": "Target user not found"}), 404

    try:
        safe_filename = secure_filename(filename)
        user_face_dir = os.path.join(KNOWN_FACES_PATH, target_user.id)
        file_path = os.path.join(user_face_dir, safe_filename)
        # Construct the relative path exactly as it would be stored in the avatar field
        relative_path_in_db = f"known_faces/{user_id}/{safe_filename}"

        new_avatar_path = target_user.avatar # Keep track if avatar changes

        if os.path.exists(file_path):
            # Check if this image *is* the current avatar BEFORE deleting
            is_current_avatar = (target_user.avatar == relative_path_in_db)

            # Delete the file
            os.remove(file_path)
            print(f"INFO: Deleted face image {file_path}")

            # If the deleted image was the avatar, find a new one
            if is_current_avatar:
                print(f"INFO: Deleted image was current avatar. Searching for replacement...")
                target_user.avatar = None # Temporarily clear it
                new_avatar_path = None # Mark as needing update

                # Find remaining image files in the directory
                remaining_files = [f for f in os.listdir(user_face_dir)
                                   if os.path.isfile(os.path.join(user_face_dir, f)) and allowed_file(f)]

                if remaining_files:
                    # Simple approach: pick the first one alphabetically
                    new_avatar_filename = sorted(remaining_files)[0]
                    new_avatar_path = f"known_faces/{user_id}/{new_avatar_filename}"
                    target_user.avatar = new_avatar_path
                    print(f"INFO: Set new avatar to first remaining image: {new_avatar_path}")
                else:
                    # No images left, avatar remains None (or set to default?)
                     # target_user.avatar = 'default_avatar.png' # Optional: set to default if desired
                    print(f"INFO: No remaining images for user {user_id}. Avatar set to None.")

            # Commit changes (including potential avatar update)
            db.session.commit()
            trigger_deepface_reindex() # Re-index after deleting image
            # Return the potentially updated avatar path
            return jsonify({
                "status": "success",
                "message": "Image deleted",
                "new_avatar": new_avatar_path # Inform client if avatar changed
            })

        else:
            # File doesn't exist, but check if avatar field points to it anyway
            if target_user.avatar == relative_path_in_db:
                 target_user.avatar = None
                 db.session.commit()
                 print(f"INFO: Reset avatar for user {user_id} as it pointed to a missing file.")
            return jsonify({"status": "error", "message": "Image file not found on disk"}), 404

    except Exception as e:
        db.session.rollback()
        print(f"ERROR deleting user face image {filename} for {user_id}: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Error deleting image"}), 500


@app.route('/api/users/<user_id>/set-avatar', methods=['PUT'])
@token_required
def set_user_avatar_from_face(user_id):
    # Auth Check: Admin or Self
    if g.current_user.role != 'Admin' and g.current_user.id != user_id: return jsonify({"status": "error", "message": "Permission denied"}), 403
    target_user = User.query.get(user_id)
    if not target_user: return jsonify({"status": "error", "message": "Target user not found"}), 404

    data = request.get_json()
    if not data or 'filename' not in data: return jsonify({"status": "error", "message": "Missing filename"}), 400

    try:
        safe_filename = secure_filename(data['filename'])
        # Construct the relative path as it should be stored/served
        relative_path = f"known_faces/{target_user.id}/{safe_filename}"
        source_face_path = os.path.join(KNOWN_FACES_PATH, target_user.id, safe_filename)

        # Verify the source image actually exists
        if not os.path.exists(source_face_path):
             print(f"ERROR set_avatar: Source file does not exist! Path: {source_face_path}")
             return jsonify({"status": "error", "message": "Source face image not found"}), 404

        # --- Just update the database field ---
        target_user.avatar = relative_path
        db.session.commit()
        print(f"INFO: Avatar for user {user_id} set to {relative_path}")
        return jsonify({"status": "success", "message": "Avatar updated", "avatar": relative_path})
        # --- No file copying needed ---

    except Exception as e:
        db.session.rollback()
        print(f"ERROR setting avatar for {user_id}: {e}")
        return jsonify({"status": "error", "message": "Error setting avatar"}), 500


@app.route('/api/logs', methods=['GET'])
@token_required
def get_logs():
    log_type = request.args.get('type') # For filtering e.g., /api/logs?type=Intruder
    query = Log.query

    if log_type and log_type != 'All':
        query = query.filter(Log.type.ilike(f'%{log_type}%')) # Case-insensitive filter

    logs = query.order_by(Log.timestamp.desc()).limit(100).all() # Get latest 100 logs

    log_list = []
    for log in logs:
        user_info = None
        utc_time = log.timestamp.replace(tzinfo=pytz.utc) # Ensure DB time is treated as UTC
        local_time = utc_time.astimezone(LOCAL_TIMEZONE)
        if log.user_id:
            log_user = User.query.get(log.user_id) # Potential performance issue if many logs
            if log_user:
                user_info = {"id": log_user.id, "name": log_user.name, "avatar": log_user.avatar}

        log_list.append({
            "id": log.id,
            # Format date and time for app
            "date": local_time.strftime('%m/%d/%Y'),
            "timestamp": local_time.strftime('%H:%M:%S'),
            "type": log.type,
            "details": log.details,
            "user": user_info,
            "image_path": f"uploads/intruder_images/{log.image_path}" if log.image_path else None # Send relative path for intruder image
        })
    return jsonify({"status": "success", "logs": log_list})


# ---> NEW Global PIN Management Endpoints (Admin Only) <---
@app.route('/api/settings/global-pin-status', methods=['GET'])
@admin_required # Only admin can check status
def get_global_pin_status():
    pin_setting = Setting.query.get('global_pin_hash')
    return jsonify({"status": "success", "is_set": bool(pin_setting)})

@app.route('/api/settings/global-pin/verify', methods=['POST'])
@admin_required # Only admin can verify the current global PIN
def verify_global_pin():
    data = request.get_json()
    if not data or 'current_pin' not in data:
        return jsonify({"status": "error", "message": "Missing current_pin"}), 400

    pin_setting = Setting.query.get('global_pin_hash')
    if not pin_setting:
        # Check if submitted pin matches the default if none is set yet
        if pwd_context.verify(data['current_pin'], pwd_context.hash(DEFAULT_GLOBAL_PIN)):
             return jsonify({"status": "success", "message": "Default PIN verified"})
        else:
             return jsonify({"status": "error", "message": "No Global PIN currently set (default mismatch)"}), 403
    elif pwd_context.verify(data['current_pin'], pin_setting.value):
        return jsonify({"status": "success", "message": "Global PIN verified"})
    else:
        return jsonify({"status": "error", "message": "Incorrect Global PIN"}), 403

@app.route('/api/settings/global-pin', methods=['PUT'])
@admin_required # Only admin can update the global PIN
def update_global_pin():
    data = request.get_json()
    if not data or 'new_pin' not in data:
        return jsonify({"status": "error", "message": "Missing new_pin"}), 400

    new_pin = data['new_pin']
    if not isinstance(new_pin, str) or len(new_pin) != 6 or not new_pin.isdigit():
         return jsonify({"status": "error", "message": "Invalid PIN format (must be 6 digits)"}), 400

    try:
        pin_setting = Setting.query.get('global_pin_hash')
        new_hash = pwd_context.hash(new_pin)
        if pin_setting:
            pin_setting.value = new_hash
        else:
            pin_setting = Setting(key='global_pin_hash', value=new_hash)
            db.session.add(pin_setting)
        db.session.commit()
        print("INFO: Global Keypad PIN updated.")
        return jsonify({"status": "success", "message": "Global PIN updated successfully"})
    except Exception as e:
        db.session.rollback()
        print(f"ERROR updating global PIN: {e}")
        return jsonify({"status": "error", "message": "Database error updating global PIN"}), 500


def perform_liveness_check(ir_dot_image_bgr):
    is_live = False
    print("Image loaded successfully.")
    img_display = ir_dot_image_bgr.copy() # For drawing intermediate steps
    gray = cv2.cvtColor(ir_dot_image_bgr, cv2.COLOR_BGR2GRAY)

    print("Loading Face Cascade...")
    face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)
    if face_cascade.empty(): print(f"ERROR: Failed to load Face Cascade from {FACE_CASCADE_PATH}"); exit()
    print("Face Cascade loaded.")

    depth_processor = None
    depth_model = None
    device = "cpu" # Use GPU if available
    print(f"INFO: Using device: {device}")
    try:
        print(f"INFO: Loading Depth Anything V2 model: {DEPTH_MODEL_NAME}...")
        depth_processor = AutoImageProcessor.from_pretrained(DEPTH_MODEL_NAME)
        depth_model = AutoModelForDepthEstimation.from_pretrained(DEPTH_MODEL_NAME).to(device)
        print("INFO: Depth model loaded successfully.")
    except Exception as model_load_error:
        print(f"ERROR: Failed to load depth model '{DEPTH_MODEL_NAME}': {model_load_error}")
        print("Ensure you have installed PyTorch and Transformers: pip install torch transformers timm")
        depth_model = None

    # --- 1. Face Detection ---
    print("Detecting faces...")
    # Adjust scaleFactor (1.1-1.4), minNeighbors (3-6), minSize
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))

    if len(faces) == 0:
        print("No face detected in the image. Cannot proceed with dot analysis on face.")
        # cv2.imshow("Original", ir_dot_image_bgr)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()
        return is_live

    # Assume the largest detected face is the one we want
    faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
    fx, fy, fw, fh = faces[0] # Bounding box of the primary face
    print(f"Face detected at: x={fx}, y={fy}, w={fw}, h={fh}")

    # Draw face rectangle on display image
    cv2.rectangle(img_display, (fx, fy), (fx+fw, fy+fh), (255, 0, 0), 2) # Blue rectangle

    # --- 2. Preprocessing (CLAHE on full grayscale) ---
    print(f"Applying CLAHE...");
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID_SIZE)
    gray = cv2.bitwise_not(gray)
    gray_enhanced = clahe.apply(gray) 
    print("CLAHE applied.")
    # cv2.imshow("1. CLAHE Enhanced", gray_enhanced); cv2.waitKey(0) # Optional view

    # --- 3. Adaptive Thresholding ---
    print("Applying Adaptive Threshold...")
    thresh = cv2.adaptiveThreshold(gray_enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, thresh_type, thresh_block_size, thresh_C)
    print("Adaptive thresholding complete.")
    # cv2.imshow("2. Thresholded after CLAHE", thresh); cv2.waitKey(0) # Optional view

    # --- 4. Morphological Opening ---
    print("Applying Morphological Opening...")
    kernel = np.ones((morph_kernel_size, morph_kernel_size), np.uint8)
    opened = cv2.erode(thresh, kernel, iterations=morph_iterations)
    opened = cv2.dilate(opened, kernel, iterations=morph_iterations)
    print("Morphological Opening complete.")
    # cv2.imshow("3. After Opening", opened); cv2.waitKey(0) # Optional view
    image_for_blob_detection = opened

    # --- 5. Blob Detection ---
    print("Detecting blobs...")
    detector = cv2.SimpleBlobDetector_create(blob_params)
    all_keypoints = detector.detect(image_for_blob_detection)
    print(f"Found {len(all_keypoints)} total blobs initially.")

    # --- 6. Filter Blobs to Keep Only Those Inside the Face ROI ---
    print("Filtering blobs within face ROI...")
    face_keypoints = []
    face_dot_coords = [] # Store (x, y) relative to image
    face_dot_intensities = [] # Store intensity at dot center

    for kp in all_keypoints:
        x, y = int(kp.pt[0]), int(kp.pt[1])
        # Check if the keypoint center is within the face bounding box
        if fx < x < fx + fw and fy < y < fy + fh:
            face_keypoints.append(kp)
            face_dot_coords.append((x, y))
            # --- Get Intensity from ORIGINAL Grayscale Image ---
            # Use the original gray image for intensity, not enhanced/thresholded
            # Clamp coordinates to be safe
            y_clamped = max(0, min(y, gray.shape[0] - 1))
            x_clamped = max(0, min(x, gray.shape[1] - 1))
            intensity = gray[y_clamped, x_clamped]
            face_dot_intensities.append(intensity)
            # Draw detected face dots on display image
            cv2.circle(img_display, (x, y), 3, (0, 255, 0), -1) # Green dots

    print(f"Found {len(face_keypoints)} blobs within the face ROI.")

    # Optional: Display intermediate result
    #cv2.imshow("Detected Face & Dots", img_display)
    #cv2.waitKey(0)


    # --- 7. Rudimentary 3D Visualization based on Intensity ---
    if len(face_dot_coords) > 5: # Need some points to plot
        print("Generating 3D plot (Intensity as Z)...")
        points = np.array(face_dot_coords)
        intensities = np.array(face_dot_intensities)

        # Normalize intensities (0-255) to a Z range (e.g., 0-1 or inverted)
        # Assuming HIGHER intensity means CLOSER (less light absorbed) -> Lower Z
        max_z_value = 50.0 
        z_coords = max_z_value * (1.0 - (intensities / 255.0))

        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection='3d')

        # Scatter plot: X, Y from image, Z from intensity
        # Invert Y-axis because image coordinates (0,0 is top-left) vs plot coordinates
        ax.scatter(points[:, 0], -points[:, 1], z_coords, c=z_coords, cmap='viridis_r', marker='.')

        # Optional: Create a rudimentary wireframe using Delaunay triangulation
        # This connects nearby points, forming triangles
        try:
            from scipy.spatial import Delaunay
            # We only have 2D points (x,y) for triangulation structure
            if len(points) >= 4: # Need at least 4 points for Delaunay in 2D
                print("Attempting Delaunay triangulation for wireframe...")
                tri = Delaunay(points) # Triangulate based on X, Y coordinates
                print(f"Triangulation found {len(tri.simplices)} triangles.")
                # Plot the wireframe using the calculated Z coordinates
                ax.plot_trisurf(points[:, 0], -points[:, 1], z_coords, triangles=tri.simplices,
                                cmap=plt.cm.viridis, #'viridis',
                                linewidth=0.2, alpha=0.5, edgecolor='grey')
            else:
                print("Not enough points for triangulation.")
        except ImportError:
            print("WARN: scipy.spatial.Delaunay not found. Cannot plot wireframe.")
        except Exception as tri_e:
            print(f"ERROR during triangulation/plotting: {tri_e}")


        ax.set_xlabel('X Coordinate (Image)')
        ax.set_ylabel('Y Coordinate (Image - Inverted)')
        ax.set_zlabel('Approx Depth (Intensity Based)')
        ax.set_title('Rudimentary 3D Point Cloud from Dot Intensity')
        # Optional: Set view angle
        # ax.view_init(elev=30, azim=-60)
        # Optional: Equal aspect ratio (might distort depth)
        # ax.set_aspect('equal')
        #plt.show() # Display the plot

    else:
        print("Not enough face dots found to generate 3D plot.")

    heatmap_norm = None # Normalized heatmap (0-1)
    heatmap_vis = None # Visualizable heatmap (0-255)
    heatmap_color_masked = None # Colored/masked heatmap for overlay
    overlay = img_display.copy() # Start overlay with original image + face dots

    if len(face_dot_coords) > 5:
        print("Generating intensity heatmap...")
        points_xy = np.array(face_dot_coords)
        intensities = np.array(face_dot_intensities)
        # Normalize intensities (0-255) -> Higher intensity = Higher value (closer?)
        # Keep this in 0-1 range
        normalized_z_intensity = intensities / 255.0

        grid_x, grid_y = np.mgrid[fx:fx+fw, fy:fy+fh]
        try:
            print(f"Interpolating {len(points_xy)} points...")
            # Using 'linear' might be faster and good enough for comparison
            heatmap_norm = griddata(points_xy, normalized_z_intensity, (grid_x, grid_y),
                                    method='linear', fill_value=np.nan) # Use NaN for fill
            heatmap_norm = heatmap_norm.T # Transpose

            # Handle NaN values (e.g., replace with median or 0) before visualization/comparison
            if np.isnan(heatmap_norm).any():
                median_val = np.nanmedian(heatmap_norm)
                if np.isnan(median_val): median_val = 0 # Handle case where all are NaN
                heatmap_norm = np.nan_to_num(heatmap_norm, nan=median_val)
                print(f"INFO: Replaced NaNs in intensity heatmap with median value: {median_val:.3f}")


            # --- Visualization Part (Optional) ---
            heatmap_vis = cv2.normalize(heatmap_norm, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            heatmap_color = cv2.applyColorMap(heatmap_vis, cv2.COLORMAP_JET)
            mask = np.zeros(ir_dot_image_bgr.shape[:2], dtype="uint8")
            cv2.rectangle(mask, (fx, fy), (fx+fw, fy+fh), 255, -1)
            # Ensure mask matches heatmap ROI dimensions
            mask_roi = mask[fy:fy+fh, fx:fx+fw]
            # Ensure heatmap color has correct dimensions BEFORE masking
            if heatmap_color.shape[:2] == mask_roi.shape:
                heatmap_color_masked = cv2.bitwise_and(heatmap_color, heatmap_color, mask=mask_roi)
                roi_overlay = overlay[fy:fy+fh, fx:fx+fw]
                if heatmap_color_masked.shape == roi_overlay.shape: # Check shape before blending
                    alpha = 0.5
                    cv2.addWeighted(heatmap_color_masked, alpha, roi_overlay, 1 - alpha, 0, roi_overlay)
                    overlay[fy:fy+fh, fx:fx+fw] = roi_overlay
                    #cv2.imshow("Intensity Heatmap Overlay", overlay)
                    #cv2.waitKey(0) # Wait after showing heatmap
                else: print("WARN: Shape mismatch between heatmap color ROI and overlay ROI.")
            else: print("WARN: Shape mismatch between heatmap color and mask ROI.")
            # -----------------------------------

            print("Intensity heatmap generated and normalized (0-1).")

        except Exception as e:
            print(f"ERROR generating intensity heatmap: {e}"); traceback.print_exc()
            heatmap_norm = None # Ensure it's None if error occurs
    else:
        print("Not enough face dots found to generate intensity heatmap.")


    # --- 8. Depth Model Prediction & Comparison ---
    is_live_final = False # Default to not live
    similarity_score = -1.0 # Default score

    if heatmap_norm is not None and depth_model is not None and depth_processor is not None:
        print("\n--- Running Depth Model & Comparison ---")
        try:
            # 1. Prepare image for Depth Model
            #    Input needs to be PIL Image in RGB format
            image_pil_rgb = Image.fromarray(cv2.cvtColor(ir_dot_image_bgr, cv2.COLOR_BGR2RGB))
            inputs = depth_processor(images=image_pil_rgb, return_tensors="pt").to(device)

            # 2. Run Depth Estimation Model
            print("Predicting depth with Depth Anything V2...")
            with torch.no_grad():
                outputs = depth_model(**inputs)
                predicted_depth = outputs.predicted_depth

            # 3. Process Output
            #    Interpolate to original size (or target heatmap size)
            prediction = torch.nn.functional.interpolate(
                predicted_depth.unsqueeze(1),
                size=image_pil_rgb.size[::-1], # H, W format
                mode="bicubic",
                align_corners=False,
            ).squeeze()

            # Move to CPU, convert to NumPy array
            depth_map_model_full = prediction.cpu().numpy()
            print(f"Model generated depth map (full size: {depth_map_model_full.shape})")

            # 4. Extract Face ROI and Normalize Model Depth Map
            #    Ensure ROI coordinates are valid
            fh_img, fw_img = gray.shape[:2]
            fx_c, fy_c, fw_c, fh_c = max(0, fx), max(0, fy), min(fw, fw_img - fx), min(fh, fh_img - fy)
            if fw_c <= 0 or fh_c <= 0: raise ValueError("Invalid face ROI dimensions after clamping")

            depth_map_model_roi = depth_map_model_full[fy_c:fy_c+fh_c, fx_c:fx_c+fw_c]

            # Normalize model's depth map ROI (0=far, 1=close or vice-versa, depends on model)
            # DepthAnything often outputs relative inverse depth (closer = higher value)
            # Normalize to 0-1 range for comparison
            depth_map_model_norm = cv2.normalize(depth_map_model_roi, None, 0, 1, cv2.NORM_MINMAX)
            print(f"Model depth map ROI extracted and normalized (shape: {depth_map_model_norm.shape})")

            # Optional: Visualize model depth map
            depth_vis = cv2.normalize(depth_map_model_roi, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
            cv2.imshow("Model Depth Map (ROI)", depth_color)
            cv2.waitKey(0)

            depth_roi = depth_map_model_roi.copy()
            vis_min_val = np.percentile(depth_roi, 5)
            vis_max_val = np.percentile(depth_roi, 95)
            print(f"DEBUG VIS: Clamping depth visualization between {vis_min_val:.2f} and {vis_max_val:.2f}")

            # Clamp values
            depth_roi[depth_roi < vis_min_val] = vis_min_val
            depth_roi[depth_roi > vis_max_val] = vis_max_val

            # Normalize the *clamped* range to 0-255
            depth_vis_clamped = cv2.normalize(depth_roi, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

            depth_color_clamped = cv2.applyColorMap(depth_vis_clamped, cv2.COLORMAP_INFERNO) # Or JET etc
            cv2.imshow("Model Depth Map (ROI - Clamped Vis)", depth_color_clamped)
            cv2.waitKey(0)


            # 5. Align and Compare Heatmap with Model Depth Map
            #    Ensure both maps cover the same ROI and have the same dimensions
            #    Our heatmap_norm already covers fx:fx+fw, fy:fy+fh
            #    Resize one to match the other if necessary (e.g., model map to heatmap size)
            target_h, target_w = heatmap_norm.shape
            if depth_map_model_norm.shape != (target_h, target_w):
                print(f"Resizing model depth map from {depth_map_model_norm.shape} to {(target_h, target_w)}...")
                depth_map_model_norm_resized = cv2.resize(depth_map_model_norm, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            else:
                depth_map_model_norm_resized = depth_map_model_norm

            # Calculate Similarity (using SSIM if available)
            if ssim is not None:
                print("Calculating Structural Similarity (SSIM)...")
                # data_range is the dynamic range of the images (1.0 since we normalized both to 0-1)
                # Ensure win_size is smaller than image dimensions and odd
                win_size = min(7, target_h // 2 * 2 + 1, target_w // 2 * 2 + 1) # Ensure odd and <= 7
                if win_size < 3 : win_size = 3 # Minimum win_size
                similarity_score, diff = ssim(heatmap_norm, depth_map_model_norm_resized, data_range=1.0, full=True, win_size=win_size)
                # Visualize difference map (optional)
                # diff = (diff * 255).astype("uint8")
                # cv2.imshow("SSIM Difference", diff)
                # cv2.waitKey(0)
            else:
                # Fallback: Calculate Mean Squared Error (lower is better)
                print("Calculating Mean Squared Error (MSE)...")
                similarity_score = np.mean((heatmap_norm - depth_map_model_norm_resized) ** 2)
                # Invert MSE for thresholding logic (higher = more similar / lower error)
                # This is tricky, maybe just use a low threshold for MSE?
                # Let's keep score as MSE, so lower is better. Threshold needs adjustment.
                # similarity_score = 1.0 / (1.0 + mse) # Example inversion


            metric_name = "SSIM" if ssim is not None else "MSE"
            print(f"Calculated Similarity Score ({metric_name}): {similarity_score:.4f}")

            # 6. Compare to Threshold
            if ssim is not None:
                # For SSIM, score is between -1 and 1, higher is more similar
                is_live = similarity_score > SIMILARITY_THRESHOLD
                print(f"Similarity Check: {similarity_score:.4f} > {SIMILARITY_THRESHOLD} ? {'PASS (Live)' if is_live else 'FAIL (Spoof?)'}")
            else:
                # For MSE lower is better.
                MSE_THRESHOLD = 0.05 #Lower means must be very similar.
                is_live = similarity_score < MSE_THRESHOLD
                print(f"Similarity Check (MSE): {similarity_score:.4f} < {MSE_THRESHOLD} ? {'PASS (Live)' if is_live else 'FAIL (Spoof?)'}")


        except Exception as compare_error:
            print(f"ERROR during depth comparison: {compare_error}")
            traceback.print_exc()
            is_live = False # Default to spoof on error
            similarity_score = -1.0

    else:
        print("Skipping depth comparison due to previous errors.")
    return is_live

# --- Endpoints for Pi Interaction ---
@app.route('/recognize', methods=['POST'])
def recognize_face_from_pi():
    # (This function combines the existing logic with logging)
    if 'file' not in request.files: return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"status": "error", "message": "No selected file"}), 400

    if file:
        try:
            in_memory_file = io.BytesIO()
            file.save(in_memory_file)
            in_memory_file.seek(0)
            file_bytes = np.asarray(bytearray(in_memory_file.read()), dtype=np.uint8)
            img_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if img_bgr is None: return jsonify({"status": "error", "message": "Could not decode image"}), 400

            print(f"INFO: Received image for recognition. Shape: {img_bgr.shape}")
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

            # --- 2. Server-Side Face Detection ---
            face_locations = []
            try:
                # Use DeepFace.extract_faces for detection ONLY.
                # Set align=False if you only need the bounding box for verification.
                # Target size can be smaller for faster detection if needed.
                # Set grayscale=False as we have color image.
                print(f"INFO: Performing server-side detection using '{DEEPFACE_DETECTOR_BACKEND}'...")
                extracted_faces = DeepFace.extract_faces(
                    img_path=img_rgb, # Use the decoded BGR image
                    detector_backend=DEEPFACE_DETECTOR_BACKEND,
                    enforce_detection=False, # IMPORTANT: Don't crash if no face found
                    align=False # We just need to know IF a face exists here
                )
                # Check if the result list is not empty and contains valid face entries
                if extracted_faces and extracted_faces[0].get('facial_area'):
                     face_locations = [face['facial_area'] for face in extracted_faces] # List of {'x':.., 'y':.., 'w':.., 'h':..}
                     print(f"INFO: Server detector found {len(face_locations)} face(s).")
                else:
                     print("INFO: Server detector found NO faces in the image.")

            except Exception as detect_err:
                 # Handle potential errors within the detector backend itself
                 print(f"ERROR: Server-side face detection failed: {detect_err}")
                 # Decide how to proceed - maybe return error or treat as no face found
                 # For now, treat as no face found
                 face_locations = []


            # --- 3. Proceed ONLY if server detected a face ---
            if not face_locations:
                 # Server couldn't confirm a face, even if Pi's Haar did.
                 # Don't log as Intruder here. Pi can decide based on this response.
                 return jsonify({"status": "success", "name": "No Face Detected by Server"})


            # --- 4. Face Confirmed - Run Recognition ---
            # Server detector found at least one face, proceed with DeepFace.find
            print(f"INFO: Face confirmed by server. Running DeepFace.find (Model: {DEEPFACE_MODEL_NAME})...")
            start_time = time.time()

            dfs = DeepFace.find(img_path=img_rgb,
                                db_path=KNOWN_FACES_PATH, # Use global path
                                model_name=DEEPFACE_MODEL_NAME,
                                enforce_detection=False,
                                detector_backend=DEEPFACE_DETECTOR_BACKEND,
                                silent=False) # Turn silent=False to see DeepFace logs

            end_time = time.time()
            processing_time = end_time - start_time
            print(f"DeepFace.find completed in {processing_time:.2f} seconds.")


            recognized_name = "Unknown"
            recognized_user_id = None

            log_details = "Access denied: Face recognized as Unknown by server." # Default log detail

            if dfs and isinstance(dfs, list) and len(dfs) > 0 and not dfs[0].empty:
                # ... (Existing logic to parse dfs, get best match, check threshold) ...
                 df = dfs[0].sort_values(by='distance'); best_match = df.iloc[0]; distance = best_match['distance']
                 if distance < DEEPFACE_RECOGNITION_THRESHOLD:
                     identity_path = best_match['identity']
                     try:
                          recognized_user_id = os.path.basename(os.path.dirname(identity_path))
                          matched_user = User.query.get(recognized_user_id)
                          recognized_name = matched_user.name if matched_user else "Known Face (ID Error)"
                          log_details = f"Access granted to {recognized_name} (Dist: {distance:.3f})." # Update log detail
                     except Exception as path_e:
                          recognized_name = "Known Face (Path Error)"
                          log_details = f"Access granted but error parsing user ID from path: {path_e}"


            # --- LOGGING ---
            log_details = ""
            log_type = ""
            user_to_log = None

            if recognized_name != "Unknown" and recognized_user_id:
                 log_type = "Access"
                 log_details = f"Access granted to {recognized_name}."
                 user_to_log = User.query.get(recognized_user_id) # Get user object for log relationship
            else:
                 log_type = "Access" # Or maybe "Access Denied"?
                 log_details = "Access denied: Face not recognized."
                 # Should we log an Intruder event here? Requires Pi to decide based on liveness.

            if log_type:
                 new_log = Log(
                     type=log_type,
                     details=log_details,
                     user_id=user_to_log.id if user_to_log else None
                 )
                 db.session.add(new_log)
                 db.session.commit()
                 print(f"Logged event: {log_type} - {log_details}")

            # Return result to Pi
            return jsonify({"status": "success", "name": recognized_name})

        except Exception as e:
            print(f"!!!!!!!!!!!!!! RECOGNIZE EXCEPTION !!!!!!!!!!!!!!")
            traceback.print_exc() # Print full traceback to server console
            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            # Log system error?
            error_log = Log(type="System", details=f"Recognition Error: {type(e).__name__}")
            db.session.add(error_log)
            db.session.commit()
            return jsonify({"status": "error", "message": f"Internal Server Error: {type(e).__name__}"}), 500

    return jsonify({"status": "error", "message": "Unknown file processing error"}), 500

# ---> MODIFIED Keypad Verification <---
@app.route('/api/keypad/verify', methods=['POST'])
def verify_keypad_code():
    # Note: No @token_required here, Pi cannot easily authenticate
    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({"status": "error", "message": "Missing code"}), 400

    entered_code = data['code']
    pin_valid = False
    log_details = f"Keypad attempt with code: {'*' * len(entered_code)}."

    # Fetch global PIN hash from settings
    pin_setting = Setting.query.get('global_pin_hash')
    current_pin_hash = None
    if pin_setting:
        current_pin_hash = pin_setting.value
    else:
        # If not set in DB, use hash of the default code
        current_pin_hash = pwd_context.hash(DEFAULT_GLOBAL_PIN)
        print(f"WARN: Global PIN not set in DB, checking against default ({DEFAULT_GLOBAL_PIN}).")

    if pwd_context.verify(entered_code, current_pin_hash):
         pin_valid = True
         log_details = "Keypad unlock successful (Global PIN)."
         print("INFO: Keypad code verified successfully (Global PIN).")
    else:
         log_details += " Incorrect Global PIN."
         print("INFO: Keypad code verification failed (Global PIN).")

    # Logging
    log_type = "Keypad Success" if pin_valid else "Keypad Failure"
    try:
        new_log = Log(type=log_type, details=log_details)
        db.session.add(new_log)
        db.session.commit()
        print(f"Logged keypad event: {log_type}")
    except Exception as e:
        db.session.rollback()
        print(f"ERROR logging keypad event after verification: {e}")

    if pin_valid:
        return jsonify({"status": "success", "message": "PIN verified"})
    else:
        return jsonify({"status": "error", "message": "Invalid PIN"}), 403 # 403 Forbidden


@app.route('/api/logs/intruder', methods=['POST'])
def log_intruder_event():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    if file and allowed_file(file.filename):
        try:
            # Create unique filename
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"intruder_{uuid.uuid4().hex}.{ext}"
            save_path = os.path.join(app.config['UPLOAD_FOLDER_INTRUDER'], filename)
            file.save(save_path)

            # Create log entry
            new_log = Log(
                type="Intruder",
                details="Potential intruder detected.",
                image_path=filename # Store relative filename
            )
            db.session.add(new_log)
            db.session.commit()
            print(f"Logged Intruder event, image saved as {filename}")
            return jsonify({"status": "success", "message": "Intruder event logged"}), 201

        except Exception as e:
            db.session.rollback()
            print(f"ERROR logging intruder event: {e}")
            return jsonify({"status": "error", "message": f"Failed to log intruder event: {e}"}), 500
    else:
        return jsonify({"status": "error", "message": "File type not allowed"}), 400


@app.route('/uploads/intruder_images/<filename>')
def serve_intruder_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER_INTRUDER'], filename)

# Serve known face images? Be careful about security/privacy implications.
# Maybe requires authentication and specific user checks.
# Example (Needs Auth):
@app.route('/known_faces/<user_id>/<filename>')
@token_required # Keep authentication!
def serve_known_face(user_id, filename):
    # Auth Check: Admin or Self (can view own face images/avatar)
    if g.current_user.role != 'Admin' and g.current_user.id != user_id:
        return jsonify({"status": "error", "message": "Permission denied to view this image"}), 403

    # --- Proceed with serving file (existing logic) ---
    user_face_dir = os.path.join(KNOWN_FACES_PATH, user_id)
    safe_filename = secure_filename(filename)
    abs_directory = os.path.abspath(user_face_dir) # For logging
    file_path = os.path.join(abs_directory, safe_filename) # For logging

    print(f"--- SERVE KNOWN_FACE / AVATAR ---") # Log route hit
    print(f"User: {user_id}, File: {filename} -> {safe_filename}")
    print(f"Serving Directory (Absolute): {abs_directory}")
    print(f"Attempting File: {file_path}")
    print(f"File Exists Check: {os.path.exists(file_path)}")

    if not os.path.isdir(user_face_dir): return jsonify({"status": "error", "message": "User directory not found"}), 404
    # Let send_from_directory handle the final file existence check and serving
    try:
        return send_from_directory(user_face_dir, safe_filename)
    except Exception as e:
        print(f"ERROR in send_from_directory for known_face {safe_filename}: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Error serving file"}), 500


# --- Main Execution ---
if __name__ == '__main__':
    with app.app_context():
        from flask import g # Import g for admin check decorator
        print("Checking database schema...")
        db.create_all() # Ensures User, Log, Setting tables exist
        print("Database schema checked/updated.")

        # Initialize default global PIN if not set
        if not Setting.query.get('global_pin_hash'):
             print(f"Setting default Global Keypad PIN ({DEFAULT_GLOBAL_PIN})...")
             default_pin_hash = pwd_context.hash(DEFAULT_GLOBAL_PIN)
             new_setting = Setting(key='global_pin_hash', value=default_pin_hash)
             db.session.add(new_setting)
             db.session.commit()
             print("Default Global PIN set.")

        # Optional: Create a default admin user if none exists
        if not User.query.filter_by(email='admin@neuralock.local').first():
             print("Creating default admin user...")
             admin = User(id=str(uuid.uuid4()), email='admin@neuralock.local', name='Admin User', role='Admin')
             admin.set_password('password') # CHANGE THIS DEFAULT PASSWORD
             db.session.add(admin)
             db.session.commit()
             print("Default admin created (email: admin@neuralock.local, pass: password)")

    print(f"Starting Flask server with Waitress...")
    from waitress import serve
    serve(app, host='0.0.0.0', port=5000, threads=8)