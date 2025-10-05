import rasterio
import numpy as np
import cv2
from scipy import ndimage

def compute_sar_height(sar_path, incidence_angle=38):  # Avg θ for IW; extract from metadata if needed
    with rasterio.open(sar_path) as src:
        vv = src.read(1).astype(np.float32)  # Backscatter
        transform = src.transform
        profile = src.profile

    # Speckle filter (simple Lee)
    vv_filtered = ndimage.median_filter(vv, size=3)

    # Edge detection for rims/roof arcs (double-bounce)
    edges = cv2.Canny((vv_filtered * 255 / np.max(vv_filtered)).astype(np.uint8), 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=50, minLineLength=20, maxLineGap=10)

    if lines is None:
        return None, profile  # No detections

    # Estimate Δr (range displacement in pixels; convert to meters at 10m res)
    delta_r_px = np.mean([np.abs(line[0][1] - line[0][3]) for line in lines])  # Vertical layover approx
    delta_r_m = delta_r_px * 10  # 10m resolution
    height_m = delta_r_m / np.sin(np.radians(incidence_angle))

    # Tank radius: Placeholder from public specs (e.g., 15m avg for Cushing); refine with detection
    radius_m = 15.0

    # Volume (cylindrical, adjust for cone if dome detected)
    volume_bbl = np.pi * radius_m**2 * height_m * 5.61458  # m³ to barrels (API gravity ~0.85)

    return {'height': height_m, 'volume': volume_bbl, 'radius': radius_m}, profile

# Example usage: heights, _ = compute_sar_height('data/Cushing_S1_VV_20250928_20251005.tif')
