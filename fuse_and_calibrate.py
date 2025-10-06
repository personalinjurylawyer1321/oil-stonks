import json
import os
import requests
import pandas as pd

def get_eia_data(api_key):
    """
    Fetches the latest weekly Cushing, OK crude oil stocks from the EIA API.

    Args:
        api_key (str): Your EIA API key.

    Returns:
        float: The latest Cushing inventory in millions of barrels, or None on failure.
    """
    if not api_key or api_key == "YOUR_KEY_HERE":
        print("Error: EIA API key not provided. Please add it to the script.")
        return None

    # Series ID for Cushing, OK Crude Oil Stocks
    series_id = "PET.W_EPC0_SAX_YCUOK_MBBL.W"
    url = f"https://api.eia.gov/v2/seriesid/{series_id}?api_key={api_key}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # The data is returned in a nested structure
        latest_data = data['response']['data'][0]
        cushing_stocks_mbbl = float(latest_data['value']) # Value is in thousands of barrels

        print(f"Successfully fetched EIA data: {cushing_stocks_mbbl} thousand barrels.")
        return cushing_stocks_mbbl * 1000 # Return in barrels

    except requests.exceptions.RequestException as e:
        print(f"Error fetching EIA data: {e}")
    except (KeyError, IndexError):
        print("Error parsing EIA API response. The data format may have changed.")

    return None

def fuse_and_calibrate(estimates_path, eia_api_key):
    """
    Fuses SAR and shadow estimates and calibrates them against EIA data.

    Args:
        estimates_path (str): Path to the JSON file with per-tank estimates.
        eia_api_key (str): Your EIA API key.

    Returns:
        dict: A dictionary with the total estimated volume and the calibrated volume.
    """
    try:
        with open(estimates_path, 'r') as f:
            tank_estimates = json.load(f)
    except FileNotFoundError:
        print(f"Error: Estimates file not found at {estimates_path}")
        return None

    total_estimated_volume = 0
    for estimate in tank_estimates:
        sar_vol = estimate.get('sar_metrics', {}).get('volume_bbl', 0)
        shadow_vol = estimate.get('shadow_metrics', {}).get('volume_bbl', 0)

        # Use a weighted average for fusion
        fused_vol = 0.7 * sar_vol + 0.3 * shadow_vol
        total_estimated_volume += fused_vol

    print(f"Total fused volume estimate: {total_estimated_volume:,.2f} barrels.")

    # Get EIA data for calibration
    eia_total_volume = get_eia_data(eia_api_key)
    if eia_total_volume is None:
        print("Could not perform calibration without EIA data.")
        return {'uncalibrated_volume': total_estimated_volume, 'calibrated_volume': None}

    # Calculate calibration factor
    if total_estimated_volume == 0:
        print("Warning: Total estimated volume is zero. Cannot calculate calibration factor.")
        calibration_factor = 1.0
    else:
        calibration_factor = eia_total_volume / total_estimated_volume

    print(f"Calibration factor: {calibration_factor:.4f}")

    calibrated_volume = total_estimated_volume * calibration_factor

    return {
        'uncalibrated_volume': total_estimated_volume,
        'calibrated_volume': calibrated_volume,
        'eia_reported_volume': eia_total_volume,
        'calibration_factor': calibration_factor
    }

if __name__ == '__main__':
    # This is a placeholder for running the script.
    # Assumes 'tank_volume_estimates.json' exists from the previous step.

    # IMPORTANT: Replace with your actual EIA API key
    EIA_API_KEY = "YOUR_KEY_HERE"

    # Create a dummy estimates file for testing
    if not os.path.exists('data'):
        os.makedirs('data')
    dummy_estimates = [
        {'tank_id': 0, 'sar_metrics': {'volume_bbl': 120000}, 'shadow_metrics': {'volume_bbl': 110000}},
        {'tank_id': 1, 'sar_metrics': {'volume_bbl': 250000}, 'shadow_metrics': {'volume_bbl': 260000}},
    ]
    estimates_file = 'data/tank_volume_estimates.json'
    with open(estimates_file, 'w') as f:
        json.dump(dummy_estimates, f)

    calibration_results = fuse_and_calibrate(estimates_file, EIA_API_KEY)

    if calibration_results:
        print("\n--- Calibration Results ---")
        for key, value in calibration_results.items():
            if isinstance(value, float):
                print(f"{key}: {value:,.2f}")
            else:
                print(f"{key}: {value}")
        print("-------------------------")