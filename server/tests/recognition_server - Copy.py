# recognition_server.py
from flask import Flask, request, jsonify
import cv2
import numpy as np
from deepface import DeepFace
import os
import warnings
import io
import time

# Suppress TensorFlow/DeepFace warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

# --- DeepFace Configuration ---
DB_PATH = "C:\\Projects\\neuralock_server\\known_faces" # !! Set path on PC !!
MODEL_NAME = "ArcFace" # Or Facenet, etc.
#DISTANCE_METRIC = "cosine"
DETECTOR_BACKEND = "opencv"
RECOGNITION_THRESHOLD = 0.4

app = Flask(__name__)

print("Loading DeepFace models...")
# Preload model (optional, but can speed up first request)
try:
    _ = DeepFace.find(img_path=np.zeros((100, 100, 3)), db_path=DB_PATH, model_name=MODEL_NAME, detector_backend='skip', silent=True)
    print("DeepFace models loaded.")
except Exception as e:
    print(f"Warning: Could not preload models. DB path correct? Error: {e}")
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database path '{DB_PATH}' not found on PC.")

@app.route('/recognize', methods=['POST'])
def recognize_face_route():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    if file:
        try:
            # Read image file into memory
            in_memory_file = io.BytesIO()
            file.save(in_memory_file)
            in_memory_file.seek(0)
            
            # Convert image stream to OpenCV format (BGR)
            file_bytes = np.asarray(bytearray(in_memory_file.read()), dtype=np.uint8)
            img_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            if img_bgr is None:
                 return jsonify({"status": "error", "message": "Could not decode image"}), 400

            # Perform face recognition
            start_time = time.time()
            print(f"Running DeepFace.find (Model: {MODEL_NAME}, DB: {DB_PATH})...")
            dfs = DeepFace.find(img_path=img_bgr, # Pass the image array
                                db_path=DB_PATH,
                                model_name=MODEL_NAME,
                                #distance_metric=DISTANCE_METRIC,
                                enforce_detection=False,
                                detector_backend=DETECTOR_BACKEND,
                                silent=True)
            
            end_time = time.time()
            processing_time = end_time - start_time
            print(f"DeepFace.find completed in {processing_time:.2f} seconds.")

            recognized_name = "Unknown"
            min_distance = float('inf')

            if dfs and not dfs[0].empty:
                df = dfs[0]
                #print(f"DEBUG: DataFrame columns: {df.columns.to_list()}")
                #print(f"DEBUG: DataFrame head:\n{df.head()}")
                df = df.sort_values(by='distance')
                if not df.empty:
                    best_match = df.iloc[0]
                    #print(f"DEBUG: Best match row:\n{best_match}")
                    distance = best_match['distance']
                    if distance < RECOGNITION_THRESHOLD:
                        identity_path = best_match['identity']
                        recognized_name = os.path.basename(os.path.dirname(identity_path))
                        min_distance = distance

            print(f"Recognition result: {recognized_name}, Distance: {min_distance if min_distance != float('inf') else 'N/A'}") # Server log
            return jsonify({"status": "success", "name": recognized_name})

        except Exception as e:
            print(f"ERROR during recognition: {e}") # Log error on server
            return jsonify({"status": "error", "message": str(e)}), 500
            
    return jsonify({"status": "error", "message": "Unknown error"}), 500

if __name__ == '__main__':
    print(f"Starting Flask server. Listening on http://0.0.0.0:5000")
    # Use host='0.0.0.0' to accept connections from other devices on the network
    app.run(host='0.0.0.0', port=5000, debug=False) # Turn debug=False for stability