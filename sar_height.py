import os
import json
import pandas as pd
import rasterio
from rasterio.windows import from_bounds
import numpy as np

# Constants
M3_TO_BBL = 6.28981  # Conversion factor from cubic meters to barrels

import re

def get_sar_metadata(sar_rtc_path):
    """
    Finds the correct metadata file by matching the scene ID from the SAR filename.
    """
    raw_dir = './data/raw'

    # 1. Extract the scene ID from the RTC filename
    # e.g., S1A_IW_GRDH_1SDV_20220428T001858_20220428T001923_042969_05208D_523E
    match = re.search(r'(S1[AB]_IW_GRDH_1S[SD]V_\w{15}_\w{15}_\w{6}_\w{6}_\w{4})', sar_rtc_path)
    if not match:
        raise ValueError(f"Could not extract scene ID from filename: {sar_rtc_path}")
    scene_id = match.group(1)
    print(f"  - Extracted Scene ID: {scene_id}")

    # 2. Search for the JSON file containing this scene ID
    for meta_file in os.listdir(raw_dir):
        if meta_file.endswith('.json') and meta_file.startswith('S1_'):
            meta_path = os.path.join(raw_dir, meta_file)
            with open(meta_path, 'r') as f:
                metadata = json.load(f)
                if metadata.get('scene_id') == scene_id:
                    print(f"  - Found matching metadata: {meta_file}")
                    # Use the mean of near and far incidence angles for the AOI
                    inc_angle = (metadata['incidence_angle_near'] + metadata['incidence_angle_far']) / 2
                    return {'incidence_angle': inc_angle}

    raise FileNotFoundError(f"No metadata file found for scene ID {scene_id} in {raw_dir}")


def estimate_tank_fill_level(tank, sar_dataset, incidence_angle):
    """
    Estimates the fill level of a single tank using the double-bounce arc method.
    """
    # Get tank properties
    tank_id = tank['tank_id']
    lon, lat = tank['longitude'], tank['latitude']
    diameter_m = tank['diameter_m']
    radius_m = diameter_m / 2

    try:
        # --- 1. Crop the SAR image to the tank's location ---
        # Define a buffer around the tank (e.g., 1.5x the diameter)
        buffer_m = diameter_m * 0.5

        # Get pixel coordinates for the bounding box
        bounds = (lon - 0.001, lat - 0.001, lon + 0.001, lat + 0.001) # A small box for transform
        window = from_bounds(*bounds, transform=sar_dataset.transform) # This is approximate, needs refinement

        # A more precise way: convert centerpoint to pixel coords first
        px, py = sar_dataset.index(lon, lat)

        # Calculate window size in pixels based on tank diameter and buffer
        pixel_res = sar_dataset.res[0]
        radius_px = int(np.ceil(radius_m / pixel_res))
        buffer_px = int(np.ceil(buffer_m / pixel_res))
        window_radius = radius_px + buffer_px

        crop_window = rasterio.windows.Window(
            px - window_radius,
            py - window_radius,
            window_radius * 2,
            window_radius * 2
        )

        # Read the SAR backscatter data (VV polarization is usually best for this)
        vv_crop = sar_dataset.read(1, window=crop_window)

        # --- 2. Find the bright arc (layover) ---
        # The layover effect causes the roof's reflection to be displaced.
        # A simple method is to find the brightest pixel in the cropped area.
        if vv_crop.size == 0:
            return {'tank_id': tank_id, 'error': 'Crop failed'}

        # Find the coordinates of the maximum value within the cropped window
        max_val_coords = np.unravel_index(np.argmax(vv_crop), vv_crop.shape)

        # The center of the crop window is (window_radius, window_radius)
        center_px = (window_radius, window_radius)

        # Calculate the displacement in pixels (this is delta_r)
        delta_r_px = np.sqrt((max_val_coords[1] - center_px[1])**2 + (max_val_coords[0] - center_px[0])**2)

        # --- 3. Convert displacement to height ---
        delta_r_m = delta_r_px * pixel_res

        # Height formula: h = Δr / sin(θ)
        # We assume the displacement is primarily in the range direction.
        height_m = delta_r_m / np.sin(np.radians(incidence_angle))

        # Assume a max shell height (e.g., 15m) to cap unrealistic values
        max_shell_height = 15.0
        height_m = min(height_m, max_shell_height)

        # --- 4. Calculate volume ---
        volume_m3 = np.pi * (radius_m**2) * height_m
        volume_bbl = volume_m3 * M3_TO_BBL

        return {
            'tank_id': tank_id,
            'fill_height_m': round(height_m, 2),
            'fill_volume_bbl': round(volume_bbl, 2),
            'latitude': lat,
            'longitude': lon,
            'error': None
        }

    except Exception as e:
        return {'tank_id': tank_id, 'error': str(e)}


def analyze_sar_for_tanks(sar_rtc_path, inventory_path):
    """
    Analyzes a single analysis-ready SAR image to estimate fill levels for all tanks in an inventory.

    Args:
        sar_rtc_path (str): Path to the RTC-processed SAR GeoTIFF file (power scale, gamma-nought).
        inventory_path (str): Path to the CSV file with tank inventory.

    Returns:
        list: A list of dictionaries, where each dictionary contains the fill-level
              estimate for a single tank.
    """
    print(f"Analyzing SAR image: {os.path.basename(sar_rtc_path)}")

    # 1. Load tank inventory
    try:
        inventory_df = pd.read_csv(inventory_path)
        print(f"Loaded inventory with {len(inventory_df)} tanks.")
    except FileNotFoundError:
        print(f"Inventory file not found at: {inventory_path}")
        return []

    # 2. Load SAR metadata to get incidence angle
    try:
        metadata = get_sar_metadata(sar_rtc_path)
        incidence_angle = metadata['incidence_angle']
        print(f"Using incidence angle: {incidence_angle:.2f} degrees")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return []

    # 3. Open SAR image and process each tank
    results = []
    with rasterio.open(sar_rtc_path) as sar_dataset:
        for index, tank in inventory_df.iterrows():
            # Check the roof type before processing
            if tank.get('roof_type') == 'floating':
                estimate = estimate_tank_fill_level(tank, sar_dataset, incidence_angle)
                if estimate.get('error'):
                    print(f"  - Failed on {estimate['tank_id']}: {estimate['error']}")
                else:
                    print(f"  - Processed {estimate['tank_id']} (floating): Height={estimate.get('fill_height_m')}m")
            else:
                # For fixed-roof tanks, we cannot determine volume, so we skip analysis.
                print(f"  - Skipping {tank['tank_id']} (fixed roof).")
                estimate = {
                    'tank_id': tank['tank_id'],
                    'fill_height_m': np.nan,
                    'fill_volume_bbl': np.nan,
                    'latitude': tank['latitude'],
                    'longitude': tank['longitude'],
                    'error': 'Skipped: fixed roof'
                }
            results.append(estimate)

    return results

if __name__ == '__main__':
    # --- Example Usage ---
    # This assumes you have run the previous steps and have the necessary files.

    # Find the most recent RTC-processed SAR image
    processed_dir = './data/processed/s1_rtc'
    # A real implementation would select a specific file to analyze.
    # Here, we just grab the first one we find.
    try:
        sar_files = [f for f in os.listdir(processed_dir) if f.endswith('_VV.tif')]
        if not sar_files:
            raise FileNotFoundError("No RTC SAR files found in processed directory.")

        latest_sar_file = os.path.join(processed_dir, sar_files[0])
        inventory_file = './data/inventory/cushing_tank_inventory.csv'

        # Run the analysis
        tank_estimates = analyze_sar_for_tanks(latest_sar_file, inventory_file)

        if tank_estimates:
            # Save results to a new CSV
            results_df = pd.DataFrame(tank_estimates)
            output_path = './data/results'
            os.makedirs(output_path, exist_ok=True)
            results_filename = os.path.join(output_path, f"sar_estimates_{os.path.basename(latest_sar_file)}.csv")
            results_df.to_csv(results_filename, index=False)

            print(f"\nAnalysis complete. Results saved to: {results_filename}")

            # Print a summary
            valid_results = results_df.dropna(subset=['fill_volume_bbl'])
            total_volume = valid_results['fill_volume_bbl'].sum()
            print(f"\nTotal estimated volume for {len(valid_results)} tanks: {total_volume:,.0f} barrels")

    except FileNotFoundError as e:
        print(f"\nError: Could not run example. {e}")
        print("Please ensure you have run the previous steps to generate the inventory and process SAR data.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")