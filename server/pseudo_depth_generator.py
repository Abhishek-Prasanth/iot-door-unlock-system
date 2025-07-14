# File: pseudo_depth_generator.py

import cv2
import numpy as np
import os
import sys


DEFAULT_HAAR_CASCADE_PATH = os.path.join(cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')


def _create_single_pseudo_depth_map(
    face_roi,
    target_display_size,
    blur_kernel_size=(41, 41),
    blur_sigma=25,
    ellipse_scale_x=0.85,
    ellipse_scale_y=0.95,
    apply_colormap=True,
    invert_colormap=True,
    colormap_type=cv2.COLORMAP_JET,
    brightness_alpha=1.0,
    brightness_beta=15,
    final_blur_kernel_size=(45,45),
    final_blur_sigma=0
    ):
    """
    Internal helper to creates a pseudo depth map effect for a single face ROI.
    Returns the processed image as a NumPy array or None on failure.
    """
    if face_roi is None or face_roi.size == 0:
        print("Error: Input face_roi is empty.")
        return None

    final_display_image = None 

    # 1. Blur
    try:
        k_w = blur_kernel_size[0] if blur_kernel_size[0] % 2 != 0 else blur_kernel_size[0] + 1
        k_h = blur_kernel_size[1] if blur_kernel_size[1] % 2 != 0 else blur_kernel_size[1] + 1
        blurred_roi = cv2.GaussianBlur(face_roi, (k_w, k_h), blur_sigma)
    except cv2.error as e:
         print(f"Error applying initial Gaussian Blur: {e}. Using original ROI.")
         blurred_roi = face_roi

    # 2. Normalize
    normalized_blurred = cv2.normalize(blurred_roi, None, 0, 255, cv2.NORM_MINMAX)
    data_for_plotting = normalized_blurred.copy()

    # 3. Mask
    h, w = data_for_plotting.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    center_x, center_y = w // 2, h // 2
    axis_x = max(1, int((w / 2) * ellipse_scale_x)) # Ensure axis > 0
    axis_y = max(1, int((h / 2) * ellipse_scale_y)) # Ensure axis > 0
    try:
        cv2.ellipse(mask, (center_x, center_y), (axis_x, axis_y), 0, 0, 360, (255), thickness=-1)
    except cv2.error as e:
        print(f"Warning: Ellipse drawing failed: {e}. Using rectangular mask.")
        mask.fill(255)

    # 4. Apply Mask (Grayscale)
    data_for_plotting = cv2.bitwise_and(data_for_plotting, data_for_plotting, mask=mask)

    # 5. Resize
    can_apply_colormap_after_resize = apply_colormap
    try:
        display_data = cv2.resize(data_for_plotting, target_display_size, interpolation=cv2.INTER_LINEAR)
        display_mask_resized = cv2.resize(mask, target_display_size, interpolation=cv2.INTER_NEAREST)
    except cv2.error as e:
        print(f"Error resizing: {e}. Cannot proceed with this ROI.")
        return None 

    # 6. Apply Colormap
    final_image_before_brightness = display_data # Default grayscale
    is_color = False

    if can_apply_colormap_after_resize:
        try:
            data_to_colorize = display_data
            if invert_colormap:
                data_to_colorize = (255 - display_data.astype(np.uint8)).astype(np.uint8)

            display_data_color = cv2.applyColorMap(data_to_colorize, colormap_type)
            display_mask_3ch = cv2.cvtColor(display_mask_resized, cv2.COLOR_GRAY2BGR)
            final_image_before_brightness = cv2.bitwise_and(display_data_color, display_mask_3ch) # Now BGR
            is_color = True

        except cv2.error as e:
             print(f"Error applying colormap: {e}. Falling back to grayscale.")
             # final_image_before_brightness remains grayscale

    # 7. Apply Brightness/Contrast Adjustment
    final_image_after_brightness = final_image_before_brightness
    if is_color and (brightness_alpha != 1.0 or brightness_beta != 0):
         try:
             
             final_image_after_brightness = cv2.convertScaleAbs(final_image_before_brightness,
                                                                alpha=brightness_alpha,
                                                                beta=brightness_beta)
             
             display_mask_3ch = cv2.cvtColor(display_mask_resized, cv2.COLOR_GRAY2BGR)
             final_image_after_brightness = cv2.bitwise_and(final_image_after_brightness, display_mask_3ch)

         except cv2.error as e:
              print(f"Error adjusting brightness/contrast: {e}")
              final_image_after_brightness = final_image_before_brightness # Revert if error

    # 8. Apply Final Blur
    final_display_image = final_image_after_brightness 
    if is_color: 
        try:
            # Ensure kernel size is odd
            k_w_final = final_blur_kernel_size[0] if final_blur_kernel_size[0] % 2 != 0 else final_blur_kernel_size[0] + 1
            k_h_final = final_blur_kernel_size[1] if final_blur_kernel_size[1] % 2 != 0 else final_blur_kernel_size[1] + 1
            if k_w_final > 0 and k_h_final > 0: 
                final_display_image = cv2.GaussianBlur(final_image_after_brightness, (k_w_final, k_h_final), final_blur_sigma)
                # Re-apply mask AFTER final blur
                display_mask_3ch = cv2.cvtColor(display_mask_resized, cv2.COLOR_GRAY2BGR)
                final_display_image = cv2.bitwise_and(final_display_image, display_mask_3ch)
            else:
                 final_display_image = final_image_after_brightness 

        except cv2.error as e:
            print(f"Error applying final Gaussian Blur: {e}")
            final_display_image = final_image_after_brightness 

    # Return the processed image array
    return final_display_image



def generate_face_pseudo_depth_maps(
    image_path,
    haar_cascade_path=DEFAULT_HAAR_CASCADE_PATH,
    face_scaleFactor=1.1,
    face_minNeighbors=5,
    face_minSize=(40, 40),
    display_size=(600, 600),
    blur_kernel_size=(41, 41),
    blur_sigma=25,
    ellipse_scale_x=0.85,
    ellipse_scale_y=0.95,
    apply_colormap=True,
    invert_colormap=True,
    colormap_type=cv2.COLORMAP_JET,
    brightness_alpha=1.0,
    brightness_beta=15,
    final_blur_kernel_size=(45,45),
    final_blur_sigma=0
    ):
    """
    Detects faces in an image and generates pseudo-depth map visualizations.

    Args:
        image_path (str): Path to the input image file.
        haar_cascade_path (str): Path to the Haar Cascade XML file for face detection.
        face_scaleFactor (float): Parameter for face detection.
        face_minNeighbors (int): Parameter for face detection.
        face_minSize (tuple): Parameter for face detection (width, height).
        display_size (tuple): Target (width, height) for the output processed images.
        blur_kernel_size (tuple): Initial blur kernel size (width, height), must be odd.
        blur_sigma (float): Initial blur sigma.
        ellipse_scale_x (float): Horizontal scale for the elliptical mask.
        ellipse_scale_y (float): Vertical scale for the elliptical mask.
        apply_colormap (bool): Whether to apply a colormap.
        invert_colormap (bool): Whether to invert colors before colormapping.
        colormap_type (int): OpenCV colormap constant (e.g., cv2.COLORMAP_JET).
        brightness_alpha (float): Contrast adjustment factor.
        brightness_beta (int): Brightness adjustment offset.
        final_blur_kernel_size (tuple): Final blur kernel size (width, height), must be odd.
        final_blur_sigma (float): Final blur sigma.


    Returns:
        tuple: A tuple containing:
            - list: A list of NumPy arrays, where each array is a processed
                    pseudo-depth map image for a detected face. Empty if no faces
                    or errors occurred.
            - np.ndarray: The original image with bounding boxes drawn around
                          detected faces (or the original image if no faces found).
            - list: A list of tuples, where each tuple is the bounding box
                    (x, y, w, h) for a detected face. Empty if no faces.
    """
    processed_images = []
    face_boxes = []
    image_with_boxes = None

    # 1. Load Cascade
    if not os.path.exists(haar_cascade_path):
        print(f"FATAL ERROR: Haar Cascade not found at {haar_cascade_path}")
        return [], None, [] # Return empty results
    face_cascade = cv2.CascadeClassifier(haar_cascade_path)

    # 2. Load Image
    if not os.path.exists(image_path):
        print(f"FATAL ERROR: Image not found at {image_path}")
        return [], None, []
    image = cv2.imread(image_path)
    if image is None:
        print(f"FATAL ERROR: Cannot read image {image_path}")
        return [], None, []

    print(f"Image loaded: '{os.path.basename(image_path)}'. Shape: {image.shape}")
    image_with_boxes = image.copy() # For drawing boxes later
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 4. Detect Faces
    faces = face_cascade.detectMultiScale(gray,
                                        scaleFactor=face_scaleFactor,
                                        minNeighbors=face_minNeighbors,
                                        minSize=face_minSize)
    print(f"Detected {len(faces)} potential face(s).")
    face_boxes = faces.tolist() # Convert numpy array to list of lists/tuples

    # 5. Process Each Face
    if len(faces) == 0:
        print("No faces detected.")
    else:
        for i, (x, y, w, h) in enumerate(faces):
            face_index = i + 1
            
            if w <= 0 or h <= 0:
                print(f"Warning: Skipping invalid face box {face_index} with W={w}, H={h}")
                continue
            face_roi_gray = gray[y:y+h, x:x+w]
            if face_roi_gray.size == 0:
                print(f"Warning: Extracted ROI for Face {face_index} is empty.")
                continue

            # Draw bounding box on the copy
            cv2.rectangle(image_with_boxes, (x, y), (x+w, y+h), (0, 255, 0), 2) # Green box

            # Generate the pseudo depth map for this ROI
            processed_img = _create_single_pseudo_depth_map(
                face_roi=face_roi_gray,
                target_display_size=display_size,
                blur_kernel_size=blur_kernel_size,
                blur_sigma=blur_sigma,
                ellipse_scale_x=ellipse_scale_x,
                ellipse_scale_y=ellipse_scale_y,
                apply_colormap=apply_colormap,
                invert_colormap=invert_colormap,
                colormap_type=colormap_type,
                brightness_alpha=brightness_alpha,
                brightness_beta=brightness_beta,
                final_blur_kernel_size=final_blur_kernel_size,
                final_blur_sigma=final_blur_sigma
            )

            if processed_img is not None:
                processed_images.append(processed_img)
            else:
                 print(f"Failed to generate map for face #{face_index}")


    return processed_images, image_with_boxes, face_boxes


# --- Example Usage ---
if __name__ == "__main__":
    # --- Configuration for Example ---
    INPUT_IMAGE = 'path/to/your/image.jpg'  # <<<--- CHANGE THIS
    CASCADE_FILE = DEFAULT_HAAR_CASCADE_PATH # Use default or specify another path

    # Check if input image exists
    if not os.path.exists(INPUT_IMAGE):
         print(f"Error: Input image '{INPUT_IMAGE}' not found for example usage.")
         sys.exit(1)

    # --- Call the main function ---
    # You can override any default processing parameters here if needed
    list_of_pseudo_depth_maps, img_with_boxes, boxes = generate_face_pseudo_depth_maps(
        image_path=INPUT_IMAGE,
        haar_cascade_path=CASCADE_FILE,
        display_size=(300, 300), # Example smaller display size
        # Example overrides:
        invert_colormap=False,
        brightness_beta=20,
        final_blur_kernel_size=(5,5), # Less final blur
        final_blur_sigma=0
    )

    # --- Display the results ---
    print(f"\nFunction returned {len(list_of_pseudo_depth_maps)} processed image(s).")

    if img_with_boxes is not None:
        cv2.imshow('Detected Faces', img_with_boxes)

    if list_of_pseudo_depth_maps:
        for i, processed_map in enumerate(list_of_pseudo_depth_maps):
            cv2.imshow(f'Pseudo Depth Map Face #{i+1}', processed_map)
    elif len(boxes) > 0:
         print("Faces were detected, but processing failed to generate maps.")

    if img_with_boxes is not None:
        print("\nPress any key while OpenCV windows are active to exit.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    else:
         print("\nCould not process image or display results.")

    print("Example finished.")