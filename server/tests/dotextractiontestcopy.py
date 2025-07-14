import cv2
import numpy as np
import os
from scipy.spatial import cKDTree # Keep for potential neighbor analysis later
import math
import traceback
import matplotlib.pyplot as plt # For 3D plot
from mpl_toolkits.mplot3d import Axes3D # Enable 3D projection
from scipy.interpolate import griddata
import torch
from transformers import AutoImageProcessor, AutoModelForDepthEstimation
from PIL import Image
from vignette_utils import apply_elliptical_vignette
from pseudo_depth_generator import generate_face_pseudo_depth_maps

try:
    # Recommended: scikit-image for SSIM
    from skimage.metrics import structural_similarity as ssim
except ImportError:
    print("WARN: scikit-image not found. Install it for SSIM comparison (`pip install scikit-image`). Falling back to basic MSE.")
    ssim = None

# --- Configuration ---
# Image Path
IMAGE_DIR = "ir_captures"
IMAGE_FILENAME = "3fkcdcnew.jpg" # <-- PUT YOUR IMAGE FILENAME HERE
IMAGE_PATH = os.path.join(IMAGE_DIR, IMAGE_FILENAME)

# Face Detection (Haar Cascade)
# Ensure this path is correct after OS reinstall/opencv-data install
FACE_CASCADE_PATH = 'C:\\Projects\\neuralock_server\\.venv\\Lib\\site-packages\\cv2\\data\\haarcascade_frontalface_default.xml'
HEATMAP_INTERPOLATION_METHOD = 'cubic'
SIMILARITY_THRESHOLD = 0.3

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

# --- Loading Image & Face Detector ---
print(f"Loading image: {IMAGE_PATH}")
img_color = cv2.imread(IMAGE_PATH)
if img_color is None: print(f"ERROR: Could not load image"); exit()
print("Image loaded successfully.")
img_display = img_color.copy() # For drawing intermediate steps
gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)

print("Loading Face Cascade...")
face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)
if face_cascade.empty(): print(f"ERROR: Failed to load Face Cascade from {FACE_CASCADE_PATH}"); exit()
print("Face Cascade loaded.")


# --- 1. Face Detection ---
print("Detecting faces...")
# Adjust scaleFactor (1.1-1.4), minNeighbors (3-6), minSize
faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(50, 50))

if len(faces) == 0:
    print("No face detected in the image. Cannot proceed with dot analysis on face.")
    cv2.imshow("Original", img_color)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    exit()

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
gray_enhanced = clahe.apply(gray) # Use original gray, not blurred maybe? Or gray_blurred = cv2.medianBlur(gray, 3) first
print("CLAHE applied.")
cv2.imshow("1. CLAHE Enhanced", gray_enhanced); cv2.waitKey(0) # Optional view

# --- 3. Adaptive Thresholding ---
print("Applying Adaptive Threshold...")
thresh = cv2.adaptiveThreshold(gray_enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, thresh_type, thresh_block_size, thresh_C)
print("Adaptive thresholding complete.")
cv2.imshow("2. Thresholded after CLAHE", thresh); cv2.waitKey(0) # Optional view

# --- 4. Morphological Opening ---
print("Applying Morphological Opening...")
kernel = np.ones((morph_kernel_size, morph_kernel_size), np.uint8)
opened = cv2.erode(thresh, kernel, iterations=morph_iterations)
opened = cv2.dilate(opened, kernel, iterations=morph_iterations)
print("Morphological Opening complete.")
cv2.imshow("3. After Opening", opened); cv2.waitKey(0) # Optional view
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
cv2.imshow("Detected Face & Dots", img_display)
cv2.waitKey(0)


# --- 7. Rudimentary 3D Visualization based on Intensity ---
if len(face_dot_coords) > 5: # Need some points to plot
    print("Generating 3D plot (Intensity as Z)...")
    points = np.array(face_dot_coords)
    intensities = np.array(face_dot_intensities)

    # Normalize intensities (0-255) to a Z range (e.g., 0-1 or inverted)
    # Assuming HIGHER intensity means CLOSER (less light absorbed) -> Lower Z
    # Adjust max_z_value as needed
    max_z_value = 50.0 # Arbitrary max depth value for visualization
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
    plt.show() # Display the plot

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
        mask = np.zeros(img_color.shape[:2], dtype="uint8")
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
                cv2.imshow("Intensity Heatmap Overlay", overlay)
                
                heatmap_color = apply_elliptical_vignette(heatmap_color,
                                              scale_x=0.85,  # Wider ellipse
                                              scale_y=0.95,  # Shorter ellipse
                                              feather_sigma=0.0)
                heatmap_color = cv2.GaussianBlur(heatmap_color, (45,45), 0)
                cv2.imshow("Heat map", heatmap_color)
                cv2.waitKey(0) # Wait after showing heatmap
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

processed_maps, original_with_boxes, face_coords = generate_face_pseudo_depth_maps(
    image_path=IMAGE_PATH,
    haar_cascade_path=FACE_CASCADE_PATH,
    # Example parameter overrides:
    display_size=(600, 600),
    apply_colormap=True,
    invert_colormap=True,
    brightness_beta=25,
    blur_sigma=20
)

if processed_maps:
    cv2.imshow("Pseudo Depth Map", processed_maps[0])
    cv2.waitKey(0)

gray_dots = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2GRAY)
gray_model = cv2.cvtColor(processed_maps[0], cv2.COLOR_BGR2GRAY)

h_dots, w_dots = gray_dots.shape
h_model, w_model = gray_model.shape

if (h_dots, w_dots) != (h_model, w_model):
    print(f"Resizing New Method map from {w_model}x{h_model} to {w_dots}x{h_dots}...")
    gray_model_resized = cv2.resize(gray_model, (w_dots, h_dots), interpolation=cv2.INTER_LINEAR) # Or INTER_CUBIC
else:
    gray_model_resized = gray_model
print("Images are now the same size.")

try:
    score_ssim, diff = ssim(gray_dots, gray_model_resized, full=True, data_range=gray_dots.max() - gray_dots.min())
    # 'diff' is an image highlighting differences, can be displayed if needed
    # diff_vis = (diff * 255).astype("uint8")
    # cv2.imshow("SSIM Difference", diff_vis)
    print(f"\nStructural Similarity Index (SSIM): {score_ssim:.4f}")
    print("(Value closer to 1 means more similar)")
except Exception as e:
    print(f"\nERROR calculating SSIM: {e}")
    print("Ensure scikit-image is installed: pip install scikit-image")
    score_ssim = None

# 2. Mean Squared Error (MSE)
#    - Measures the average squared difference between pixel values.
#    - Lower value means more similar (0 means identical).
#    - Sensitive to overall brightness/contrast differences.
try:
    mse = np.mean((gray_dots.astype("float") - gray_model_resized.astype("float")) ** 2)
    print(f"\nMean Squared Error (MSE): {mse:.2f}")
    print("(Lower value means more similar)")
except Exception as e:
    print(f"\nERROR calculating MSE: {e}")
    mse = None

# --- Liveness Decision Placeholder ---
# You need to determine a threshold based on experiments
# with known live faces vs known spoofs (e.g., photos on screens).
# SSIM is often a good candidate.
if score_ssim is not None:
    # --- TUNE THIS THRESHOLD ---
    SSIM_LIVENESS_THRESHOLD = 0.6
    # ---------------------------
    is_live_estimate = score_ssim > SSIM_LIVENESS_THRESHOLD
    print(f"\nLiveness Estimate (SSIM > {SSIM_LIVENESS_THRESHOLD}): {'Likely LIVE' if is_live_estimate else 'Likely SPOOF / Dissimilar'}")
elif mse is not None:
     # MSE thresholding is trickier as scale depends on image content
     # Lower MSE is better.
     MSE_LIVENESS_THRESHOLD = 4000 # EXAMPLE - Needs tuning!
     is_live_estimate = mse < MSE_LIVENESS_THRESHOLD
     print(f"\nLiveness Estimate (MSE < {MSE_LIVENESS_THRESHOLD}): {'Likely LIVE' if is_live_estimate else 'Likely SPOOF / Dissimilar'}")


final_dots_img = cv2.drawKeypoints(img_color, face_keypoints, np.array([]), (0,255,0), cv2.DRAW_MATCHES_FLAGS_DEFAULT)
# Update text based on final liveness decision
text = f"Final Liveness: {'LIVE' if is_live_final else 'SPOOF?'} (Score: {similarity_score:.3f})"
color = (0, 255, 0) if is_live_final else (0, 0, 255)
cv2.putText(final_dots_img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
cv2.imshow("Final Detected Dots & Liveness", final_dots_img)
# --- Cleanup ---
cv2.destroyAllWindows()
print("Finished.")