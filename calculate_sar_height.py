import rasterio
import numpy as np
import cv2

def get_sar_height(sar_path, tank_bbox, incidence_angle):
    """
    Calculates the height of a tank from SAR layover.

    Args:
        sar_path (str): The path to the Sentinel-1 GeoTIFF image.
        tank_bbox (tuple): The bounding box of the tank (x, y, w, h).
        incidence_angle (float): The incidence angle in degrees.

    Returns:
        dict: A dictionary containing the calculated height and volume, or None on failure.
    """
    if incidence_angle is None or incidence_angle <= 0:
        print("Warning: Invalid incidence angle. Cannot calculate SAR height.")
        return None

    with rasterio.open(sar_path) as src:
        window = rasterio.windows.from_bounds(*tank_bbox, src.transform)
        tank_image = src.read(1, window=window)

        # Normalize the backscatter data for edge detection
        # This handles the log-scaled data correctly
        normalized_image = cv2.normalize(tank_image, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)

        # Use Canny edge detection
        edges = cv2.Canny(normalized_image, 50, 150)

        # A more robust method for finding layover:
        # We expect two bright, parallel lines from the tank top and bottom.
        # The distance between them in the range direction is the layover.
        # This is a simplified approach; a more advanced method would use template matching
        # or analyze the phase information if available.

        # For this implementation, we'll find the horizontal projection of the edges
        horizontal_projection = np.sum(edges, axis=0)

        # Find peaks in the projection, which correspond to the bright layover lines
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(horizontal_projection, height=np.max(horizontal_projection)*0.5, distance=5)

        if len(peaks) < 2:
            return None # Not enough distinct features for layover calculation

        # Assume the two largest peaks are the tank walls
        delta_r_px = np.abs(peaks[0] - peaks[1])

        resolution = src.res[0] # Assuming square pixels
        delta_r_m = delta_r_px * resolution

        # Calculate height using the layover formula
        height_m = delta_r_m / np.cos(np.radians(90 - incidence_angle))

        # Radius from bounding box
        radius_m = (tank_bbox[2] / 2) * resolution

        # Volume calculation
        volume_bbl = np.pi * (radius_m ** 2) * height_m * 6.28981 # m^3 to barrels

        return {
            'height_m': height_m,
            'volume_bbl': volume_bbl,
            'layover_m': delta_r_m,
            'radius_m': radius_m
        }
    return None