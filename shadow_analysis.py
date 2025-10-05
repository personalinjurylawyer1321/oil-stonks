import os
import json
import pandas as pd
import rasterio
from rasterio.windows import from_bounds
import numpy as np
from skimage.color import rgb2gray
from skimage.filters import threshold_otsu

# Constants
M3_TO_BBL = 6.28981
MAX_SHELL_HEIGHT_M = 15.0  # Assumed maximum height of a tank shell in meters

def get_optical_metadata(optical_image_path):
    """Loads the corresponding JSON metadata file for an optical image."""
    base_name = os.path.basename(optical_image_path).split('.')[0]
    raw_dir = './data/raw'
    meta_path = os.path.join(raw_dir, f"{base_name}.json")

    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Metadata file not found for {optical_image_path}. Expected at: {meta_path}")

    with open(meta_path, 'r') as f:
        metadata = json.load(f)

    if not all(k in metadata for k in ['sun_azimuth', 'sun_elevation']):
        raise ValueError(f"Metadata for {optical_image_path} is missing sun angle information.")

    return metadata

def estimate_tank_shadow_fill(tank, optical_dataset, sun_azimuth, sun_elevation):
    """
    Estimates the fill level of a single tank by measuring its shadow length.
    """
    tank_id = tank['tank_id']
    lon, lat = tank['longitude'], tank['latitude']
    diameter_m = tank['diameter_m']
    radius_m = diameter_m / 2

    try:
        # --- 1. Crop the image to the tank's location ---
        pixel_res = optical_dataset.res[0]
        px, py = optical_dataset.index(lon, lat)

        # Define a window large enough to contain the tank and its shadow
        buffer_px = int(np.ceil((MAX_SHELL_HEIGHT_M / np.tan(np.radians(sun_elevation))) / pixel_res)) + int(radius_m / pixel_res) + 20
        window_radius = int(radius_m / pixel_res) + buffer_px

        crop_window = rasterio.windows.Window(
            px - window_radius,
            py - window_radius,
            window_radius * 2,
            window_radius * 2
        )

        # Read RGB bands and create a grayscale image
        # Using S2 bands: B2, B3, B4 (Blue, Green, Red)
        rgb_crop = optical_dataset.read([1, 2, 3], window=crop_window)
        gray_crop = rgb2gray(np.moveaxis(rgb_crop, 0, -1))

        # --- 2. Create a shadow mask ---
        # Shadows are dark, so we can use a simple threshold.
        # Otsu's method finds an optimal threshold value automatically.
        thresh = threshold_otsu(gray_crop)
        shadow_mask = gray_crop < thresh

        # --- 3. Measure shadow length in the correct direction ---
        # The shadow is cast opposite to the sun's azimuth.
        shadow_azimuth = (sun_azimuth + 180) % 360

        # Convert azimuth to a direction vector (y, x) in the image
        # Angle is from North, clockwise. Image coords are (row, col) ~ (y, -x) from top-left.
        angle_rad = np.deg2rad(shadow_azimuth)
        direction_vector = np.array([np.cos(angle_rad), np.sin(angle_rad)])

        # Find all shadow pixel coordinates relative to the crop center
        center_px = np.array([window_radius, window_radius])
        shadow_pixels = np.argwhere(shadow_mask)

        if shadow_pixels.size == 0:
            return {'tank_id': tank_id, 'error': 'No shadow pixels found'}

        # Project shadow pixels onto the direction vector
        vectors_from_center = shadow_pixels - center_px
        projections = np.dot(vectors_from_center, direction_vector)

        # Find the maximum projection distance beyond the tank's radius
        radius_px = radius_m / pixel_res
        max_projection = np.max(projections[projections > radius_px]) if np.any(projections > radius_px) else 0

        shadow_length_px = max_projection - radius_px
        shadow_length_px = max(0, shadow_length_px) # Ensure shadow length is not negative
        shadow_length_m = shadow_length_px * pixel_res

        # --- 4. Calculate height and volume ---
        exposed_wall_height = shadow_length_m * np.tan(np.radians(sun_elevation))
        exposed_wall_height = min(exposed_wall_height, MAX_SHELL_HEIGHT_M) # Cap at max height

        fill_height_m = MAX_SHELL_HEIGHT_M - exposed_wall_height

        volume_m3 = np.pi * (radius_m**2) * fill_height_m
        volume_bbl = volume_m3 * M3_TO_BBL

        return {
            'tank_id': tank_id,
            'fill_height_m': round(fill_height_m, 2),
            'fill_volume_bbl': round(volume_bbl, 2),
            'shadow_length_m': round(shadow_length_m, 2),
            'error': None
        }

    except Exception as e:
        return {'tank_id': tank_id, 'error': str(e)}

def analyze_optical_for_tanks(optical_image_path, inventory_path):
    """
    Analyzes a single optical image to estimate fill levels for all tanks in an inventory.
    """
    print(f"Analyzing optical image: {os.path.basename(optical_image_path)}")

    # 1. Load inventory and metadata
    try:
        inventory_df = pd.read_csv(inventory_path)
        metadata = get_optical_metadata(optical_image_path)
        sun_azimuth = metadata['sun_azimuth']
        sun_elevation = metadata['sun_elevation']
        print(f"Loaded inventory ({len(inventory_df)} tanks) and metadata (Sun Az: {sun_azimuth:.1f}°, El: {sun_elevation:.1f}°).")
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        return []

    # 2. Open optical image and process each tank
    results = []
    with rasterio.open(optical_image_path) as optical_dataset:
        for index, tank in inventory_df.iterrows():
            estimate = estimate_tank_shadow_fill(tank, optical_dataset, sun_azimuth, sun_elevation)
            results.append(estimate)
            if estimate['error']:
                print(f"  - Failed on {estimate['tank_id']}: {estimate['error']}")
            else:
                print(f"  - Processed {estimate['tank_id']}: Height={estimate['fill_height_m']}m")

    return results

if __name__ == '__main__':
    # --- Example Usage with Dummy Data ---
    # This block allows the script to be run for testing purposes.

    optical_file = './data/raw/S2_dummy_optical.tif'
    inventory_file = './data/inventory/cushing_tank_inventory.csv'

    if not os.path.exists(optical_file) or not os.path.exists(inventory_file):
        print("Error: Required dummy files not found.")
        print("Please ensure 'S2_dummy_optical.tif', 'S2_dummy_optical.json', and 'cushing_tank_inventory.csv' exist.")
    else:
        # Run the analysis
        tank_estimates = analyze_optical_for_tanks(optical_file, inventory_file)

        if tank_estimates:
            # Save results to a new CSV
            results_df = pd.DataFrame(tank_estimates)
            output_path = './data/results'
            os.makedirs(output_path, exist_ok=True)
            results_filename = os.path.join(output_path, f"optical_estimates_{os.path.basename(optical_file)}.csv")
            results_df.to_csv(results_filename, index=False)

            print(f"\nAnalysis complete. Results saved to: {results_filename}")

            # Print a summary
            valid_results = results_df.dropna(subset=['fill_volume_bbl'])
            total_volume = valid_results['fill_volume_bbl'].sum()
            print(f"\nTotal estimated volume for {len(valid_results)} tanks: {total_volume:,.0f} barrels")