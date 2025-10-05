import rasterio
import cv2
import numpy as np
from skimage import measure

def extract_shadow_height(optical_path, thermal_path=None, sun_elevation=45):  # α from metadata
    with rasterio.open(optical_path) as src:
        rgb = src.read([1, 2, 3])  # R,G,B (S2: B4,B3,B2; L8: SR_B4,SR_B3,SR_B2)
        rgb = np.moveaxis(rgb, 0, -1)  # HWC
        transform = src.transform

    # Convert to HSV for shadow detection (dark, low saturation)
    hsv = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2HSV)
    shadow_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 50]))  # Tune thresholds

    # Morphological ops for 10-30m res (larger kernel)
    kernel = np.ones((5, 5), np.uint8)  # Adjust for res
    shadow_mask = cv2.morphologyEx(shadow_mask, cv2.MORPH_CLOSE, kernel)

    # Find shadow lengths (assume vertical shadows; connect to tanks via proximity)
    contours, _ = cv2.findContours(shadow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Largest shadow (proxy for tank group)
    largest_contour = max(contours, key=cv2.contourArea)
    shadow_length_px = cv2.boundingRect(largest_contour)[3]  # Height of bbox
    shadow_length_m = shadow_length_px * (10 if 'S2' in optical_path else 30)  # Res-aware

    height_m = shadow_length_m * np.tan(np.radians(sun_elevation))

    # Thermal adjustment if L8 (filled tanks warmer)
    if thermal_path:
        with rasterio.open(thermal_path) as tsrc:
            thermal = tsrc.read(1)
            avg_temp = np.mean(thermal[measure.find_contours(shadow_mask, 0.5)[0]]) if contours else 20
            height_adjust = 0.5 if avg_temp > 25 else -0.5  # Proxy: warmer = fuller/higher
            height_m += height_adjust

    radius_m = 15.0  # From specs
    volume_bbl = np.pi * radius_m**2 * height_m * 5.61458

    return {'height': height_m, 'volume': volume_bbl, 'radius': radius_m}

# Usage: shadow_heights = extract_shadow_height('data/Cushing_S2_RGB_*.tif', 'data/Cushing_L8_RGB_Thermal_*.tif')
