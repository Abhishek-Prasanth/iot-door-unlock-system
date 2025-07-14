from deepface import DeepFace
import matplotlib.pyplot as plt
import cv2 # OpenCV is often used by detector backends

# --- Configuration ---
# Replace this with the actual path to your image file
image_path = "ir_captures\\bgrtest.png" # Using your path from the error

# Choose a face detector backend. Common options:
# 'opencv', 'ssd', 'mtcnn', 'retinaface', 'mediapipe'
detector = 'mtcnn'
try:
    face_objs = DeepFace.extract_faces(
    img_path=image_path,
    detector_backend=detector,
    enforce_detection=True,
    anti_spoofing = True
    )
    for face_obj in face_objs:
        print(face_obj["is_real"])
    if face_objs[0]["is_real"]:
        print("It is bool.")
except:
    print("False")

