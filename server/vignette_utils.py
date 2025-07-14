import cv2
import numpy as np
import os 

def apply_elliptical_vignette(image, scale_x=0.85, scale_y=0.85, feather_sigma=30.0):
    """
    Applies an elliptical vignette (black border) to an image.

    Args:
        image (np.ndarray): The input image (BGR or grayscale).
        scale_x (float): Scale factor for the ellipse width relative to image width (0.0 to 1.0+).
                         Smaller values mean a smaller visible horizontal area.
        scale_y (float): Scale factor for the ellipse height relative to image height (0.0 to 1.0+).
                         Smaller values mean a smaller visible vertical area.
        feather_sigma (float): Standard deviation for the Gaussian blur used to soften
                               the ellipse edge. Higher values create a softer, wider fade.
                               Set to 0 or less for a hard edge.

    Returns:
        np.ndarray: The image with the elliptical vignette applied, or None if input is invalid.
    """
    if image is None:
        print("Error: Input image is None.")
        return None

    h, w = image.shape[:2]
    is_color = len(image.shape) == 3

    # 1. Create a float mask (0.0 to 1.0)
    # Start with a black background and draw a white ellipse (value 1.0)
    mask = np.zeros((h, w), dtype=np.float32)

    # Calculate ellipse parameters
    center_x, center_y = w // 2, h // 2
    # Ensure axes are at least 1 pixel
    axis_x = max(1, int((w / 2) * scale_x))
    axis_y = max(1, int((h / 2) * scale_y))

    # Draw the white filled ellipse (value 1.0) onto the black mask (value 0.0)
    try:
        cv2.ellipse(mask, (center_x, center_y), (axis_x, axis_y), 0, 0, 360, (1.0), thickness=-1)
    except cv2.error as e:
         print(f"Warning: Could not draw ellipse (image might be too small?): {e}. Using full mask.")
         mask.fill(1.0) # Fallback: make everything visible if ellipse fails

    # 2. Apply feathering by blurring the mask
    if feather_sigma > 0:
        # Use a kernel size appropriate for the sigma (rule of thumb: ~6*sigma + 1)
        ksize = int(6 * feather_sigma) + 1
        ksize = ksize if ksize % 2 != 0 else ksize + 1 # Ensure kernel size is odd
        mask = cv2.GaussianBlur(mask, (ksize, ksize), feather_sigma)
        # Blurring might slightly change values, ensure it stays within [0, 1] if needed
        # np.clip(mask, 0.0, 1.0, out=mask) # Usually not necessary for 0->1 mask blur

    # 3. Apply the mask to the image using element-wise multiplication
    # Convert mask to have the same number of channels as the image if it's color
    if is_color:
        mask_3ch = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR) # Replicate channel
        # Multiply image (converted to float) by the mask
        result_float = image.astype(np.float32) * mask_3ch
    else: # Grayscale image
        result_float = image.astype(np.float32) * mask

    # 4. Convert back to original data type (e.g., uint8)
    # Clip values to ensure they are within the valid range (e.g., 0-255 for uint8)
    # This is important as float multiplication might slightly exceed the range
    result = np.clip(result_float, 0, 255).astype(image.dtype)

    return result

# --- Example Usage ---
if __name__ == "__main__":
    # --- Configuration for Example ---
    IMAGE_PATH = 'path/to/your/image.jpg'  # <<<--- CHANGE THIS TO YOUR IMAGE FILE
    VISIBLE_SCALE_X = 0.8  # Make ellipse width 80% of image width
    VISIBLE_SCALE_Y = 0.9  # Make ellipse height 90% of image height
    FEATHER_STRENGTH = 50.0 # How soft the edge is (higher = softer/wider fade)

    # --- Load Image ---
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: Image file not found at '{IMAGE_PATH}'")
        exit()

    img = cv2.imread(IMAGE_PATH)

    if img is None:
        print(f"Error: Could not read image from '{IMAGE_PATH}'")
        exit()

    # --- Apply the Vignette ---
    vignetted_img = apply_elliptical_vignette(
        img,
        scale_x=VISIBLE_SCALE_X,
        scale_y=VISIBLE_SCALE_Y,
        feather_sigma=FEATHER_STRENGTH
    )

    # --- Display ---
    if vignetted_img is not None:
        cv2.imshow('Original Image', img)
        cv2.imshow('Elliptical Vignette', vignetted_img)
        print(f"Applied vignette: scale=({VISIBLE_SCALE_X},{VISIBLE_SCALE_Y}), feather={FEATHER_STRENGTH}")
        print("Press any key to exit.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()