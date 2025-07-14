import cv2
import numpy as np
import matplotlib.pyplot as plt
import os
import sys

# --- Configuration ---
IMAGE_PATH = 'ir_captures\\xoo50t.jpg' # <<<--- CHANGE THIS
HAAR_CASCADE_PATH = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
DISPLAY_SIZE = (600, 600)

# --- Blur Parameters ---
BLUR_KERNEL_SIZE = (41, 41)
BLUR_SIGMA = 25

# --- Masking Parameters ---
ELLIPSE_SCALE_X = 0.85
ELLIPSE_SCALE_Y = 0.95

# --- Visualization ---
DEFAULT_APPLY_COLORMAP = True
DEFAULT_INVERT_COLORMAP = True # Set to False to match your reference image's colors (Blue=Deep, Red=Shallow)
DEFAULT_COLORMAP_TYPE = cv2.COLORMAP_JET

# <<< --- NEW Brightness/Contrast Parameters --- >>>
# alpha: Contrast adjustment (1.0 = no change, >1 = increase)
BRIGHTNESS_ALPHA = 1.0
# beta: Brightness adjustment (0 = no change, >0 = increase brightness)
# --- TRY INCREASING THIS VALUE ---
BRIGHTNESS_BETA = 15 # Start with a small positive value (e.g., 10, 15, 20, 30)
# <<< --- End New Parameters --- >>>


# --- Function Definition ---
def create_pseudo_depth_map(face_roi,
                            target_display_size,
                            title="Pseudo Depth Map",
                            apply_colormap=True,
                            invert_colormap=True,
                            colormap_type=cv2.COLORMAP_JET,
                            brightness_alpha=1.0, # New arg
                            brightness_beta=15):  # New arg
    """Creates a pseudo depth map effect with brightness adjustment."""
    if face_roi is None or face_roi.size == 0:
        print(f"Skipping '{title}' (no data).")
        return

    # 1. Blur
    try:
        k_w = BLUR_KERNEL_SIZE[0] if BLUR_KERNEL_SIZE[0] % 2 != 0 else BLUR_KERNEL_SIZE[0] + 1
        k_h = BLUR_KERNEL_SIZE[1] if BLUR_KERNEL_SIZE[1] % 2 != 0 else BLUR_KERNEL_SIZE[1] + 1
        blurred_roi = cv2.GaussianBlur(face_roi, (k_w, k_h), BLUR_SIGMA)
    except cv2.error as e:
         print(f"Error blurring: {e}.")
         blurred_roi = face_roi

    # 2. Normalize
    normalized_blurred = cv2.normalize(blurred_roi, None, 0, 255, cv2.NORM_MINMAX)
    data_for_plotting = normalized_blurred.copy()

    # 3. Mask
    h, w = data_for_plotting.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    center_x, center_y = w // 2, h // 2
    axis_x = int((w / 2) * ELLIPSE_SCALE_X)
    axis_y = int((h / 2) * ELLIPSE_SCALE_Y)
    try:
        cv2.ellipse(mask, (center_x, center_y), (axis_x, axis_y), 0, 0, 360, (255), thickness=-1)
    except cv2.error as e:
        print(f"Warning: Ellipse failed: {e}.")
        mask.fill(255)

    # 4. Apply Mask (Grayscale)
    data_for_plotting = cv2.bitwise_and(data_for_plotting, data_for_plotting, mask=mask)

    # 5. Resize
    can_apply_colormap_after_resize = apply_colormap
    try:
        display_data = cv2.resize(data_for_plotting, target_display_size, interpolation=cv2.INTER_LINEAR)
        display_mask_resized = cv2.resize(mask, target_display_size, interpolation=cv2.INTER_NEAREST)
    except cv2.error as e:
        print(f"Error resizing: {e}")
        display_data = data_for_plotting
        display_mask_resized = mask
        if apply_colormap:
             print("Disabling colormap due to resize error.")
             can_apply_colormap_after_resize = False

    # 6. Apply Colormap (Optional)
    final_image_before_brightness = display_data # Default grayscale
    plot_title = title + " (Grayscale)"
    is_color = False

    if can_apply_colormap_after_resize:
        try:
            data_to_colorize = display_data
            if invert_colormap:
                data_to_colorize = (255 - display_data.astype(np.uint8)).astype(np.uint8)

            display_data_color = cv2.applyColorMap(data_to_colorize, colormap_type)
            display_mask_3ch = cv2.cvtColor(display_mask_resized, cv2.COLOR_GRAY2BGR)
            final_image_before_brightness = cv2.bitwise_and(display_data_color, display_mask_3ch) # Now BGR
            plot_title = title + (" (Colormap - Inverted)" if invert_colormap else " (Colormap)")
            is_color = True

        except cv2.error as e:
             print(f"Error applying colormap: {e}. Falling back to grayscale.")
             # final_image_before_brightness remains grayscale

    # <<< --- 7. Apply Brightness/Contrast Adjustment (AFTER colormap) --- >>>
    final_display_image = final_image_before_brightness # Start with previous step result
    if is_color and (brightness_alpha != 1.0 or brightness_beta != 0):
         try:
             print(f"  Adjusting brightness/contrast: alpha={brightness_alpha}, beta={brightness_beta}")
             final_display_image = cv2.convertScaleAbs(final_image_before_brightness,
                                                      alpha=brightness_alpha,
                                                      beta=brightness_beta)
             # Re-apply mask AFTER brightness adjustment to prevent border effects
             # (convertScaleAbs might affect black areas slightly)
             display_mask_3ch = cv2.cvtColor(display_mask_resized, cv2.COLOR_GRAY2BGR)
             final_display_image = cv2.bitwise_and(final_display_image, display_mask_3ch)
             final_display_image = cv2.GaussianBlur(final_display_image, (45,45),0)
             cv2.imshow('final fantasy',final_display_image)
             return final_display_image

         except cv2.error as e:
              print(f"Error adjusting brightness/contrast: {e}")
              final_display_image = final_image_before_brightness # Revert if error
    # <<< --- End Brightness Adjustment --- >>>


    # 8. Plotting
    plt.figure()
    if len(final_display_image.shape) == 3:
         plt.imshow(cv2.cvtColor(final_display_image, cv2.COLOR_BGR2RGB))
    else:
         plt.imshow(final_display_image, cmap='gray')

    plt.title(plot_title)
    plt.xticks([])
    plt.yticks([])


# --- Main Execution ---
# (Load cascade, Load image, Detect faces - unchanged)
# 1. Load Cascade
if not os.path.exists(HAAR_CASCADE_PATH): print(f"FATAL: Haar Cascade not found at {HAAR_CASCADE_PATH}"); sys.exit(1)
face_cascade = cv2.CascadeClassifier(HAAR_CASCADE_PATH)
# 2. Load Image
if not os.path.exists(IMAGE_PATH): print(f"FATAL: Image not found at {IMAGE_PATH}"); sys.exit(1)
image = cv2.imread(IMAGE_PATH)
if image is None: print(f"FATAL: Cannot read image {IMAGE_PATH}"); sys.exit(1)
print(f"Image loaded: '{IMAGE_PATH}'. Shape: {image.shape}")
image_display = image.copy()
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
# 4. Detect Faces
faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
print(f"\nDetected {len(faces)} potential face(s).")

# 5. Process Each Face
processed_rois = []
if len(faces) == 0:
    print("No faces detected.")
else:
    for i, (x, y, w, h) in enumerate(faces):
        face_index = i + 1
        # print(f"\n--- Processing Face #{face_index} at Rect [x={x}, y={y}, w={w}, h={h}] ---")
        if w <= 0 or h <= 0: continue
        face_roi_gray = gray[y:y+h, x:x+w]
        if face_roi_gray.size == 0: continue
        cv2.rectangle(image_display, (x, y), (x+w, y+h), (255, 0, 0), 2)
        processed_rois.append((f"Pseudo Depth Face #{face_index}", face_roi_gray))

# --- Display Results ---
cv2.imshow('Detected Faces', image_display)
cv2.waitKey(1)
if processed_rois:
    print(f"\nGenerating {len(processed_rois)} Pseudo Depth Map Image(s)...")
    for title, roi_data in processed_rois:
        # --- Pass the new brightness args ---
        create_pseudo_depth_map(roi_data,
                                DISPLAY_SIZE,
                                title,
                                DEFAULT_APPLY_COLORMAP,
                                DEFAULT_INVERT_COLORMAP,
                                DEFAULT_COLORMAP_TYPE,
                                BRIGHTNESS_ALPHA,  # Pass alpha
                                BRIGHTNESS_BETA)   # Pass beta
    plt.show()
else:
     if len(faces) > 0: print("\nNo valid face ROIs extracted.")

print("\nDisplaying processed versions of the face patches.")
print(f"Colormap: {'ON' if DEFAULT_APPLY_COLORMAP else 'OFF'}, Inverted: {'YES' if DEFAULT_APPLY_COLORMAP and DEFAULT_INVERT_COLORMAP else 'NO'}, Brightness Beta: {BRIGHTNESS_BETA}")
print("Press any key in 'Detected Faces' window to exit.")
cv2.waitKey(0)
cv2.destroyAllWindows()
print("Program finished.")