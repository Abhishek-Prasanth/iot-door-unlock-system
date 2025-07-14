# camera_script.py (Pi side)

import time
import cv2
from picamera2 import Picamera2
import requests
import os
import sys
import numpy as np
import threading
from gpiozero import Button, OutputDevice 
import traceback 
import RPi.GPIO as GPIO

# Web Server Imports
from flask import Flask, jsonify, make_response, Response
from werkzeug.serving import make_server

# --- Configuration ---
FRAME_WIDTH = 1600
FRAME_HEIGHT = 900
HAAR_CASCADE_PATH = '/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml'
MIN_FACE_SIZE = (300, 300)
PC_SERVER_IP = "" # !! REPLACE !!
PC_SERVER_PORT = 5000
PC_SERVER_URL = f"http://{PC_SERVER_IP}:{PC_SERVER_PORT}"
RECOGNIZE_URL = f"{PC_SERVER_URL}/recognize"
LOG_INTRUDER_URL = f"{PC_SERVER_URL}/api/logs/intruder"
VERIFY_KEYPAD_URL = f"{PC_SERVER_URL}/api/keypad/verify"
PI_SERVER_HOST = '0.0.0.0'
PI_SERVER_PORT = 8080
PI_STREAMING_PORT = 8000 # Port Flask will stream video on

FACE_DETECT_DELAY = 2.0
CAPTURE_INTERVAL = 0.5 
COOLDOWN_SECONDS_ON_UNLOCK = 30
PROJECTOR_ON_DELAY = 0.08

# Keypad Configuration
entered_code = ""
KEYPAD_LAYOUT = [ ["1","2","3","A"],["4","5","6","B"],["7","8","9","C"],["*","0","#","D"] ]
ROW_PINS_BCM = [26, 19, 13, 6]
COL_PINS_BCM = [21, 20, 16, 12]

# Cooldown & Verification Configuration
COOLDOWN_PERIOD_SECONDS = 10
last_recognition_time = 0
REQUIRED_STREAK = 3
MAX_STREAK_TIME_DIFF = 1.5
last_match_name = None
match_streak_count = 0
last_match_time = 0

# --- Global Flags & Locks ---
keypad_unlocked = False
main_loop_running = True
keypad_thread_stop_flag = threading.Event()
streaming_active = False
streaming_lock = threading.Lock()
latest_frame_lock = threading.Lock()
latest_frame_for_stream = None

face_detected_first_time = None # Timestamp of first face detection
awaiting_server_response = False

# --- GPIO Zero Setup ---
RELAY_PIN = 17 # For Projector
LOCK_RELAY = 24 #Ffor Lock
GPIO.setmode(GPIO.BCM)
GPIO.setup(LOCK_RELAY, GPIO.OUT, initial=GPIO.LOW)

try:
    print("INFO: Initializing GPIO using gpiozero...")
    rows = [Button(pin, pull_up=True) for pin in ROW_PINS_BCM]
    cols = [OutputDevice(pin, initial_value=True) for pin in COL_PINS_BCM]
    print("INFO: Projector Relay initialized.")
    print("INFO: GPIO initialized successfully.")
except Exception as e:
    print(f"FATAL ERROR: Could not initialize GPIO pins using gpiozero: {e}")
    traceback.print_exc()
    sys.exit(1)

# --- Logging Helper Function (Intruder) ---
def log_intruder_to_server(image_bytes):
    files = {'file': ('intruder.jpg', image_bytes, 'image/jpeg')}
    try:
        log_thread = threading.Thread(target=requests.post, args=(LOG_INTRUDER_URL,), kwargs={'files': files, 'timeout': 10})
        log_thread.daemon = True
        log_thread.start()
        print("INFO: Sent intruder log request to server.")
    except Exception as e:
        print(f"ERROR: Failed to start intruder log thread: {e}")

# --- Keypad Scanning Function ---
def read_keypad_gpiozero():
    for c, col_device in enumerate(cols):
        col_device.off(); #time.sleep(0.001)
        for r, row_button in enumerate(rows):
            if row_button.is_pressed:
                col_device.on(); return KEYPAD_LAYOUT[r][c]
        col_device.on()
    return None

# --- Keypad Monitor Thread Function ---
def keypad_monitor_thread_func():
    global entered_code, keypad_unlocked, last_recognition_time
    print("INFO: Keypad monitor thread started.")
    last_key_state = None
    debounce_time = 0.05
    while not keypad_thread_stop_flag.is_set():
        pressed_key = read_keypad_gpiozero()
        if pressed_key is not None:
            if last_key_state is None: last_key_state = pressed_key
        else:
            if last_key_state is not None:
                key = last_key_state; 
                last_key_state = None
                if keypad_unlocked: continue
                if key == "#":
                    if not entered_code: continue
                    print(f"INFO: Verifying keypad code {'*' * len(entered_code)}...")
                    payload = {"code": entered_code}; entered_code = ""
                    try:
                        response = requests.post(VERIFY_KEYPAD_URL, json=payload, timeout=5)
                        if response.status_code == 200 and response.json().get("status") == "success":
                            print("***** KEYPAD UNLOCK: GRANTED *****"); keypad_unlocked = True; last_recognition_time = time.time() + COOLDOWN_SECONDS_ON_UNLOCK
                            GPIO.output(LOCK_RELAY, GPIO.HIGH)
                            time.sleep(5)
                            GPIO.output(LOCK_RELAY, GPIO.LOW)
                        elif response.status_code == 403: print("Keypad DENIED - Incorrect Code (Server)")
                        else: print(f"Keypad FAILED - Server Error (HTTP {response.status_code})")
                        try: print(f"Server Response: {response.text}")
                        except: pass
                    except Exception as e: print(f"Keypad FAILED - Request Error: {e}")
                elif key == "*": print("INFO: Keypad Code Cleared"); entered_code = ""
                else:
                    if len(entered_code) < 6: entered_code += key
        time.sleep(debounce_time)
    print("INFO: Keypad monitor thread stopped.")

# --- 3D liveness check placeholder (for testig only)---
def check_3d_liveness(ir_frame):
    # print("DEBUG: 3D Liveness Check...")
    time.sleep(0.05); return True

# --- Pi Flask Web Server ---
pi_flask_app = Flask(__name__)

# --- Stream Generation Function ---
def generate_stream_frames():
    global main_loop_running, streaming_active, latest_frame_for_stream
    last_frame_time = 0
    target_fps = 15
    frame_delay = 1.0 / target_fps
    print("DEBUG: Stream Generator Thread Started")
    frame_count = 0
    while main_loop_running:
        frame_to_encode = None; stream_now = False
        with streaming_lock: stream_now = streaming_active
        if stream_now:
            with latest_frame_lock:
                if latest_frame_for_stream is not None: frame_to_encode = latest_frame_for_stream.copy()
            if frame_to_encode is not None:
                try:
                    ret, buffer = cv2.imencode('.jpg', frame_to_encode, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        frame_count += 1
                        if frame_count % (target_fps * 2) == 1: print(f"DEBUG: Yielding stream frame {frame_count}, {len(frame_bytes)} bytes") # Log every ~2s
                        yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    else: print("WARN: cv2.imencode failed in stream generator")
                except Exception as e: print(f"ERROR generating stream frame: {e}")
                # Control FPS
                current_time = time.time(); sleep_time = frame_delay - (current_time - last_frame_time)
                if sleep_time > 0: time.sleep(sleep_time)
                last_frame_time = current_time
            else: time.sleep(0.05) 
        else: time.sleep(0.1) 
    print("INFO: Exiting stream frame generator.")

@pi_flask_app.route('/stream')
def video_feed():
    print("INFO (Flask): Client connected to /stream endpoint.") 
    return Response(generate_stream_frames(), mimetype='multipart/x-mixed-replace; boundary=frame', headers={'Cache-Control': 'no-cache, no-store, must-revalidate','Pragma': 'no-cache','Expires': '0'})

@pi_flask_app.route('/start_stream', methods=['POST', 'GET'])
def handle_start_stream():
    global streaming_active
    with streaming_lock: streaming_active = True; print("INFO (Flask): START STREAM activated.")
    return jsonify({"status": "success", "streaming": True})

@pi_flask_app.route('/stop_stream', methods=['POST', 'GET'])
def handle_stop_stream():
    global streaming_active, latest_frame_for_stream
    with streaming_lock: streaming_active = False; print("INFO (Flask): STOP STREAM activated.")
    with latest_frame_lock: latest_frame_for_stream = None
    return jsonify({"status": "success", "streaming": False})

# --- Flask Server Thread ---
class ServerThread(threading.Thread):
    def __init__(self, app, host, port):
        threading.Thread.__init__(self); self.server = make_server(host, port, app, threaded=True); self.ctx = app.app_context(); self.ctx.push()
    def run(self): print(f"INFO: Starting Pi Flask server on http://{PI_SERVER_HOST}:{PI_SERVER_PORT}"); self.server.serve_forever(); print("INFO: Pi Flask server loop exited.")
    def shutdown(self): print("INFO: Shutting down Pi Flask server..."); self.server.shutdown()

# --- Main Recognition and Capture Loop Function ---
def recognition_and_capture_loop():
    global main_loop_running, keypad_unlocked, last_recognition_time, match_streak_count, last_match_name, last_match_time
    global latest_frame_for_stream, streaming_active
    global face_detected_first_time, awaiting_server_response
    picam2 = None 
    face_cascade = None 

    try: # Initialize Camera and Haar Cascade
        print("INFO: Initializing PiCamera2..."); picam2 = Picamera2(); config = picam2.create_preview_configuration(main={"size": (FRAME_WIDTH, FRAME_HEIGHT), "format": "RGB888"}, controls={"FrameRate": 30.0}); picam2.configure(config); picam2.start(); print("INFO: PiCamera2 initialized."); time.sleep(2.0)
        print("INFO: Loading Haar Cascade..."); face_cascade = cv2.CascadeClassifier(HAAR_CASCADE_PATH);
        if face_cascade.empty(): raise RuntimeError(f"Failed Haar Cascade: {HAAR_CASCADE_PATH}")
        print("INFO: Haar Cascade loaded.")
    except Exception as e: print(f"FATAL ERROR init: {e}"); main_loop_running = False; return

    print("INFO: Starting main loop...")
    loop_count = 0
    while main_loop_running:
        loop_count += 1
        current_time = time.time()
        display_frame = None; status_label = "Scanning..."; status_color = (255, 255, 255) 

        try:
            frame_rgb = picam2.capture_array()
            if frame_rgb is None: time.sleep(0.1); continue
            display_frame = frame_rgb.copy() 

            # Update frame for streaming if active
            with streaming_lock: stream_now = streaming_active
            if stream_now:
                 with latest_frame_lock: latest_frame_for_stream = frame_rgb

            # --- Main State Machine ---
            if awaiting_server_response:
                status_label = "Verifying..."
                status_color = (255, 150, 0) # Orange
            elif keypad_unlocked:
                status_label = "Unlocked (Keypad)"; status_color = (0, 255, 255)
                if current_time > last_recognition_time: keypad_unlocked = False; print("INFO: Keypad unlock cooldown finished.")
            elif current_time < last_recognition_time: # Face unlock cooldown
                status_label = "Cooldown Active"; status_color = (255, 165, 0)
            else: # Ready to detect
                status_label = "Scanning..."; status_color = (255, 255, 255) # White
                frame_gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY); frame_gray = cv2.equalizeHist(frame_gray)
                faces = face_cascade.detectMultiScale(frame_gray, 1.1, 5, minSize=(60, 60))

                if len(faces) > 0: # Face detected
                    fx, fy, fw, fh = faces[0] 
                    # Draw rectangle
                    cv2.rectangle(display_frame, (fx, fy), (fx+fw, fy+fh), (0, 255, 255), 1) # Yellow box for detection

                    if face_detected_first_time is None:
                        # First time seeing a face in this sequence
                        print("INFO: Initial face detected. Waiting for delay...")
                        face_detected_first_time = current_time
                        status_label = "Face Detected..."
                        status_color = (255, 255, 0) # Yellow
                    elif current_time >= (face_detected_first_time + FACE_DETECT_DELAY):
                        print("INFO: Face confirmed after delay. Starting capture sequence...")
                        status_label = "Capturing..."
                        status_color = (0, 150, 255)
                        awaiting_server_response = True
                        face_detected_first_time = None # Reset timer

                        # --- Capture Sequence Thread ---
                        capture_thread = threading.Thread(
                            target=capture_and_send_sequence,
                            args=(picam2, frame_rgb.copy())
                        )
                        capture_thread.start()
                        # -----------------------------
                else: 
                    if face_detected_first_time is not None:
                         print("INFO: Face lost during delay. Resetting timer.")
                    face_detected_first_time = None

            # --- Display Status on OpenCV Window ---
            if display_frame is not None:
                 code_display = "*" * len(entered_code) if entered_code else ""; cv2.putText(display_frame, f"Code: {code_display}", (10, FRAME_HEIGHT - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 200), 1)
                 cv2.putText(display_frame, f"Status: {status_label}", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
                 cv2.imshow("Camera Feed (Pi)", display_frame)
            else: print("WARN: display_frame is None in loop.")

            # --- Handle Quit Key ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): main_loop_running = False; break
            time.sleep(0.02)

        except Exception as loop_error:
             print(f"\nERROR in main loop: {loop_error}"); traceback.print_exc(); time.sleep(1)

    # --- Main Loop Cleanup ---
    print("INFO: Exiting main recognition loop.")
    if picam2 is not None and picam2.is_open: print("INFO: Stopping PiCamera2..."); picam2.stop(); picam2.close()
    print("INFO: Destroying OpenCV windows..."); cv2.destroyAllWindows(); 

def capture_and_send_sequence(picam2_instance, first_frame_rgb):
    global awaiting_server_response, last_recognition_time, keypad_unlocked
    global RELAY_PIN, PROJECTOR_ON_DELAY
    
    captured_files_dict = {}
    capture_success = True
    
    try:
        # 1. Capture IR Frame with Projector
        print("CAPTURE SEQ: Turning Projector ON...")
        projector_relay = OutputDevice(RELAY_PIN, active_high=True, initial_value=False)
        projector_relay.on(); time.sleep(PROJECTOR_ON_DELAY)
        print("CAPTURE SEQ: Capturing IR Frame...")
        ir_frame_rgb = picam2_instance.capture_array("main")
        print("CAPTURE SEQ: Turning Projector OFF...")
        projector_relay.off()
        projector_relay.close()
        if ir_frame_rgb is None: raise ValueError("Failed to capture IR frame")
        print("CAPTURE SEQ: Encoding IR Frame...")
        ret_ir, encoded_ir = cv2.imencode(".jpg", cv2.cvtColor(ir_frame_rgb, cv2.COLOR_RGB2BGR))
        
        if ret_ir: captured_files_dict['ir_image'] = ('ir.jpg', encoded_ir.tobytes(), 'image/jpeg')
        else: raise ValueError("Failed to encode IR frame")

        # 2. Store first RGB frame (immediate)
        print("CAPTURE SEQ: Encoding RGB Frame 1...")
        ret, encoded1 = cv2.imencode(".jpg", cv2.cvtColor(first_frame_rgb, cv2.COLOR_RGB2BGR))
        if ret: captured_files_dict['rgb_image_1'] = ('rgb1.jpg', encoded1.tobytes(), 'image/jpeg')
        else: raise ValueError("Failed to encode RGB frame 1")

        # 3. Capture RGB Frame 2 (after delay)
        print(f"CAPTURE SEQ: Waiting {CAPTURE_INTERVAL}s...")
        time.sleep(CAPTURE_INTERVAL)
        print("CAPTURE SEQ: Capturing RGB Frame 2...")
        rgb_frame2 = picam2_instance.capture_array("main")
        if rgb_frame2 is None: raise ValueError("Failed to capture RGB frame 2")
        print("CAPTURE SEQ: Encoding RGB Frame 2...")
        ret2, encoded2 = cv2.imencode(".jpg", cv2.cvtColor(rgb_frame2, cv2.COLOR_RGB2BGR))
        
        if ret2: captured_files_dict['rgb_image_2'] = ('rgb2.jpg', encoded2.tobytes(), 'image/jpeg')
        else: raise ValueError("Failed to encode RGB frame 2")
        

        # 4. Capture RGB Frame 3 (after delay)
        print(f"CAPTURE SEQ: Waiting {CAPTURE_INTERVAL}s...")
        time.sleep(CAPTURE_INTERVAL)
        print("CAPTURE SEQ: Capturing RGB Frame 3...")
        rgb_frame3 = picam2_instance.capture_array("main")
        if rgb_frame3 is None: raise ValueError("Failed to capture RGB frame 3")
        print("CAPTURE SEQ: Encoding RGB Frame 3...")
        ret3, encoded3 = cv2.imencode(".jpg", cv2.cvtColor(rgb_frame3, cv2.COLOR_RGB2BGR))
        if ret3: captured_files_dict['rgb_image_3'] = ('rgb3.jpg', encoded3.tobytes(), 'image/jpeg')
        else: raise ValueError("Failed to encode RGB frame 3")
        # -------------------------------

    except Exception as cap_err:
        print(f"ERROR during capture sequence: {cap_err}"); traceback.print_exc()
        capture_success = False
        if projector_relay.is_active: projector_relay.off()

    # --- Send Captured Images to Server ---
    required_keys = ['ir_image', 'rgb_image_1', 'rgb_image_2', 'rgb_image_3']
    if capture_success and all(key in captured_files_dict for key in required_keys):
        print(f"CAPTURE SEQ: Sending {len(captured_files_dict)} images to server...")
        try:
            
            response = requests.post(RECOGNIZE_URL, files=captured_files_dict, timeout=30)
            response.raise_for_status()
            result = response.json()
            print(f"CAPTURE SEQ: Server response: {result}")

            # ... (Process response as before: check status, name, liveness_failed) ...
            if result.get("status") == "success":
                recognized_name = result.get("name", "Error")
                if recognized_name not in ["Unknown", "Error", ...]:
                     print(f"***** FACE UNLOCK GRANTED ({recognized_name}) *****")
                     last_recognition_time = time.time() + COOLDOWN_SECONDS_ON_UNLOCK
                     GPIO.output(LOCK_RELAY, GPIO.HIGH)
                     time.sleep(5)
                     GPIO.output(LOCK_RELAY, GPIO.LOW)
                else: print(f"INFO: Access denied by server: {recognized_name}")
            elif result.get("liveness_failed"): print("WARN: Server reported LIVENESS CHECK FAILED.")
            else: print(f"ERROR: Server returned error status: {result.get('message')}")

        # ... (Handle requests exceptions) ...
        except Exception as e: print(f"ERROR: Failed sending/processing server response: {e}"); traceback.print_exc()
    else:
         print(f"ERROR: Capture sequence incomplete ({len(captured_files_dict)}/{len(required_keys)} images). Not sending.")

    print("CAPTURE SEQ: Sequence finished.")
    awaiting_server_response = False


# =========== Main Program Execution ==========
if __name__ == "__main__":
    server_thread = None; kpd_thread = None
    try:
        print("INFO: Starting Keypad Monitor Thread...")
        keypad_thread_stop_flag.clear(); kpd_thread = threading.Thread(target=keypad_monitor_thread_func, daemon=True); kpd_thread.start()

        print("INFO: Starting Pi Command Server Thread...")
        pi_server_thread = ServerThread(pi_flask_app, PI_SERVER_HOST, PI_SERVER_PORT); pi_server_thread.daemon = True; pi_server_thread.start()

        recognition_and_capture_loop()

    except KeyboardInterrupt: print("\nINFO: KeyboardInterrupt received. Stopping..."); main_loop_running = False
    except Exception as e: print(f"\nFATAL ERROR in main execution: {e}"); traceback.print_exc(); main_loop_running = False
    finally:
        print("\nINFO: Initiating final cleanup...")
        main_loop_running = False 
        if kpd_thread and kpd_thread.is_alive(): print("INFO: Signaling Keypad..."); keypad_thread_stop_flag.set(); kpd_thread.join(timeout=1.0);
        if 'pi_server_thread' in locals() and pi_server_thread and pi_server_thread.is_alive(): print("INFO: Signaling Pi server..."); pi_server_thread.shutdown(); pi_server_thread.join(timeout=2.0);

        print("INFO: Closing GPIO devices...");
        try:
            for r_btn in rows: r_btn.close()
            for c_dev in cols: c_dev.close()
            if 'relay' in locals(): projector_relay.off(); projector_relay.close()
        except Exception as e: print(f"WARN: Error closing GPIO devices: {e}")

        print("INFO: Application shutdown complete.")