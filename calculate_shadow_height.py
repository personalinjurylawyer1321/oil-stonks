import rasterio
import cv2
import numpy as np

def get_shadow_height(image_path, tank_bbox, sun_elevation):
    """
    Calculates the height of a tank from its shadow in an optical image.

    Args:
        image_path (str): The path to the Sentinel-2 GeoTIFF image.
        tank_bbox (tuple): The bounding box of the tank (x, y, w, h).
        sun_elevation (float): The sun elevation angle in degrees.

    Returns:
        dict: A dictionary containing the calculated height and volume, or None on failure.
    """
    if sun_elevation is None or sun_elevation <= 0:
        print("Warning: Invalid sun elevation. Cannot calculate shadow height.")
        return None

    with rasterio.open(image_path) as src:
        # Read the image data just for the bounding box area
        window = rasterio.windows.from_bounds(*tank_bbox, src.transform)
        tank_image = src.read([1, 2, 3], window=window)
        tank_image = np.moveaxis(tank_image, 0, -1) # to HWC

        # The image is already uint8, so no need for scaling
        hsv = cv2.cvtColor(tank_image, cv2.COLOR_RGB2HSV)

        # Shadow detection in HSV space (low value/brightness)
        # These thresholds may need further tuning
        shadow_mask = cv2.inRange(hsv, (0, 0, 0), (180, 255, 60))

        # Clean up the mask
        kernel = np.ones((3, 3), np.uint8)
        shadow_mask = cv2.morphologyEx(shadow_mask, cv2.MORPH_CLOSE, kernel)

        # Find the longest shadow contour
        contours, _ = cv2.findContours(shadow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        # A more robust way to find shadow length:
        # Find the major axis of the largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest_contour) < 10: # Filter out small noisy detections
            return None

        rect = cv2.minAreaRect(largest_contour)
        (x, y), (width, height), angle = rect
        shadow_length_px = max(width, height)

        # Get resolution from the image metadata
        resolution = src.res[0]
        shadow_length_m = shadow_length_px * resolution

        # Calculate height using trigonometry
        height_m = shadow_length_m * np.tan(np.radians(sun_elevation))

        # Assuming tank radius is half the bounding box width
        radius_m = (tank_bbox[2] / 2) * resolution

        # Calculate volume
        volume_bbl = np.pi * (radius_m ** 2) * height_m * 6.28981 # m^3 to barrels

        return {
            'height_m': height_m,
            'volume_bbl': volume_bbl,
            'shadow_length_m': shadow_length_m,
            'radius_m': radius_m
        }
    return None