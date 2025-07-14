import cv2
import numpy as np
import os
from scipy.spatial import cKDTree
import math
import itertools
import traceback # Ensure traceback is imported

# --- Configuration ---
# ... (Keep your existing configurations) ...
IMAGE_DIR = "ir_captures"; IMAGE_FILENAME = "3fkcdc.jpg"; IMAGE_PATH = os.path.join(IMAGE_DIR, IMAGE_FILENAME)
CLAHE_CLIP_LIMIT = 4.0; CLAHE_TILE_GRID_SIZE = (20, 20)
# ... (Keep Blob Detector Params - start with loosened ones from previous step) ...
params = cv2.SimpleBlobDetector_Params(); params.filterByColor = True; params.blobColor = 255; params.filterByArea = True; params.minArea = 2; params.maxArea = 150; params.filterByCircularity = True; params.minCircularity = 0.4; params.filterByConvexity = True; params.minConvexity = 0.60; params.filterByInertia = True; params.minInertiaRatio = 0.1;
NEIGHBOR_RADIUS_LIVENESS = 25; MIN_DOTS_FOR_ANALYSIS = 20; LIVENESS_STD_DEV_THRESHOLD = 1.5


# --- Loading Image ---
# ... (Load image as before) ...
print(f"Loading image: {IMAGE_PATH}"); img = cv2.imread(IMAGE_PATH); # ... error check ... ; img_display = img.copy()

BLUR_KERNEL_SIZE = 3 # Odd number (3 or 5)

# --- 1. Preprocessing ---
print("Preprocessing..."); gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY);
# Initial noise reduction (optional but often good)
# gray_blurred_initial = cv2.medianBlur(gray, 3)
gray_blurred_initial = cv2.bitwise_not(gray) # Try without initial blur first

# Apply CLAHE
print(f"Applying CLAHE...");
# --- TUNE CLAHE ---
clahe_clip_limit = 3.0 # Lowered clip limit
clahe_tile_grid_size = (16, 16) # Smaller grid? Or try larger like (32,32)
# -----------------
clahe = cv2.createCLAHE(clipLimit=clahe_clip_limit, tileGridSize=clahe_tile_grid_size);
gray_enhanced = clahe.apply(gray_blurred_initial); # Apply to blurred or original gray
print("CLAHE applied.")
cv2.imshow("1. CLAHE Enhanced", gray_enhanced)
cv2.waitKey(0) # Wait

# Optional Blur AFTER CLAHE
# gray_enhanced_blurred = cv2.GaussianBlur(gray_enhanced, (BLUR_KERNEL_SIZE, BLUR_KERNEL_SIZE), 0)
# image_for_thresh = gray_enhanced_blurred
image_for_thresh = gray_enhanced # Use CLAHE output directly first

# --- 2. Adaptive Thresholding ---
print("Applying Adaptive Threshold...")
# --- TUNE Adaptive Threshold ---
block_size = 31 # Try larger block size
C = 7           # Increase C to try and separate merged dots
# ----------------------------
# Note: Use THRESH_BINARY if dots are BRIGHTER than local average after CLAHE+Blur
# Use THRESH_BINARY_INV if dots are DARKER than local average after CLAHE+Blur
# Looking at your CLAHE image, dots are bright, so use THRESH_BINARY
thresh = cv2.adaptiveThreshold(image_for_thresh, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, # <-- CHANGED to BINARY
                               block_size, C)
print("Adaptive thresholding complete.")
cv2.imshow("2. Thresholded after CLAHE", thresh)
print("-> Displaying Thresholded Image. Press any key...")
cv2.waitKey(0) # Wait

# --- 3. Morphological Operations (Optional but recommended) ---
print("Applying Morphological Opening (Optional)...")
kernel_size = 3
kernel = np.ones((kernel_size, kernel_size), np.uint8)
# Erode first to remove noise/thin connections
opened = cv2.erode(thresh, kernel, iterations=1)
# Dilate after to restore size of remaining objects
opened = cv2.dilate(opened, kernel, iterations=1) # Use 'opened' from now on
print("Morphological Opening complete.")
cv2.imshow("3. After Opening", opened)
print("-> Displaying After Opening. Press any key...")
cv2.waitKey(0) # Wait
image_for_blob_detection = opened # Use the cleaned image for blobs

# --- 4. Setup Blob Detector ---
# Remember to adjust blobColor based on the final binary image!
# If dots are WHITE in 'opened' image (from THRESH_BINARY), use blobColor = 255
# If dots are BLACK in 'opened' image (from THRESH_BINARY_INV), use blobColor = 0
print("Setting up Blob Detector...")
params = cv2.SimpleBlobDetector_Params()
params.filterByColor = True; params.blobColor = 255 # <--- ADJUST if using INV threshold
# ... Rest of blob params (tune based on 'opened' image) ...
params.filterByArea = True; params.minArea = 20; params.maxArea = 200
params.filterByCircularity = True; params.minCircularity = 0.7
params.filterByConvexity = True; params.minConvexity = 0.80
params.filterByInertia = True; params.minInertiaRatio = 0.5
detector = cv2.SimpleBlobDetector_create(params)

# --- 5. Detect Blobs ---
print("Detecting blobs...")
keypoints = detector.detect(image_for_blob_detection) # Detect on 'opened' image
print(f"Found {len(keypoints)} blobs.")

# --- 6. Liveness Analysis (if enough dots) ---
print(f"Analyzing local pattern variance..."); dot_coords = np.array([kp.pt for kp in keypoints], dtype=np.float32); is_live = False; pattern_std_dev = 0.0 # Defaults
if len(dot_coords) > 1: # Check added previously
    try: # Add try-except around KDTree/analysis
        kdtree = cKDTree(dot_coords); all_neighbor_distances = []; valid_points_for_analysis = 0
        for i, point in enumerate(dot_coords):
            neighbors_indices = kdtree.query_ball_point(point, r=NEIGHBOR_RADIUS_LIVENESS)
            neighbors_indices = [idx for idx in neighbors_indices if idx != i]
            if len(neighbors_indices) >= 2 : valid_points_for_analysis += 1; neighbor_coords = dot_coords[neighbors_indices]; distances = np.sqrt(np.sum((neighbor_coords - point)**2, axis=1)); all_neighbor_distances.extend(distances)
        if valid_points_for_analysis < MIN_DOTS_FOR_ANALYSIS // 2 : print(f"WARN: Only {valid_points_for_analysis} points had enough neighbors."); is_live = False; pattern_std_dev = 0.0
        elif not all_neighbor_distances: print("WARN: No neighbor distances."); is_live = False; pattern_std_dev = 0.0
        else:
            pattern_std_dev = np.std(all_neighbor_distances); mean_dist = np.mean(all_neighbor_distances)
            print(f"Liveness Analysis: Points Analyzed={valid_points_for_analysis}, Mean Neighbor Dist={mean_dist:.2f}, Std Dev={pattern_std_dev:.3f}")
            is_live = pattern_std_dev > LIVENESS_STD_DEV_THRESHOLD
            print(f"Liveness Result: {'LIVE' if is_live else 'SPOOF (or Flat)'} (Threshold={LIVENESS_STD_DEV_THRESHOLD})")
    except Exception as analysis_error:
         print(f"ERROR during liveness analysis: {analysis_error}")
         traceback.print_exc()
         # Continue to display detected points even if analysis failed
else: print("WARN: Not enough points for KDTree variance analysis.")


# --- 7. Display Final Results ---
final_dots_img = cv2.drawKeypoints(img, keypoints, np.array([]), (0,255,0), cv2.DRAW_MATCHES_FLAGS_DEFAULT) # Draw on original image
text = f"Liveness: {'LIVE' if is_live else 'SPOOF?'} (StdDev: {pattern_std_dev:.3f})"
color = (0, 255, 0) if is_live else (0, 0, 255)
cv2.putText(final_dots_img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
cv2.imshow("Final Detected Dots & Liveness", final_dots_img)
print("Displaying final results. Press any key in the FINAL window to exit.")
cv2.waitKey(0) # Wait indefinitely on the final window
cv2.destroyAllWindows()
print("Finished.")