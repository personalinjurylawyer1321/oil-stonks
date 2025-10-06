import json
import os
import requests

def get_previous_eia_data(api_key):
    """
    Fetches the second-to-last weekly Cushing, OK crude oil stocks from the EIA API.
    This serves as the baseline for calculating the weekly change.
    """
    if not api_key or api_key == "YOUR_KEY_HERE":
        print("Error: EIA API key not provided.")
        return None

    series_id = "PET.W_EPC0_SAX_YCUOK_MBBL.W"
    url = f"https://api.eia.gov/v2/seriesid/{series_id}?api_key={api_key}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Get the second latest data point
        previous_data = data['response']['data'][1]
        previous_stocks_bbl = float(previous_data['value']) * 1000 # Convert from MBBL to BBL

        print(f"Successfully fetched previous week's EIA data: {previous_stocks_bbl:,.0f} barrels.")
        return previous_stocks_bbl

    except requests.exceptions.RequestException as e:
        print(f"Error fetching previous EIA data: {e}")
    except (KeyError, IndexError):
        print("Error parsing previous EIA API response.")
    return None

def get_api_consensus_placeholder():
    """
    Placeholder for fetching the API consensus report.
    In a real system, this would scrape data from a news source or use a paid API.
    Returns the expected change in barrels.
    """
    # Example: API expects a 1.2 million barrel build
    print("Using placeholder API consensus: +1.2M barrels")
    return 1_200_000

def generate_trading_signal(calibration_results_path, eia_api_key):
    """
    Generates a trading signal based on the calibrated volume and gating rules.
    """
    try:
        with open(calibration_results_path, 'r') as f:
            results = json.load(f)
    except FileNotFoundError:
        print(f"Error: Calibration results file not found at {calibration_results_path}")
        return

    our_estimate = results.get('calibrated_volume')
    eia_reported = results.get('eia_reported_volume')

    if our_estimate is None or eia_reported is None:
        print("Cannot generate signal without calibrated and EIA volumes.")
        return

    # --- Gating Rules ---
    # Rule 1: Check coverage (placeholder - assumes we observed >85% of capacity)
    CUSHING_TOTAL_CAPACITY = 95_000_000 # Approx. 95M barrels
    if eia_reported < (CUSHING_TOTAL_CAPACITY * 0.85):
        print("Signal Failed: Observed capacity is less than 85% of total. No signal.")
        return

    # Get previous week's data to calculate the change
    previous_eia = get_previous_eia_data(eia_api_key)
    if previous_eia is None:
        return

    our_predicted_change = our_estimate - previous_eia

    # Rule 2: Check if the change is significant
    MIN_CHANGE_THRESHOLD = 2_000_000 # 2 million barrels
    if abs(our_predicted_change) < MIN_CHANGE_THRESHOLD:
        print(f"Signal Failed: Predicted change ({our_predicted_change:,.0f}) is below the {MIN_CHANGE_THRESHOLD:,.0f} barrel threshold. No signal.")
        return

    # Rule 3: Check divergence from API consensus
    api_consensus_change = get_api_consensus_placeholder()
    divergence = abs(our_predicted_change - api_consensus_change)
    MIN_DIVERGENCE_THRESHOLD = 1_000_000 # 1 million barrels
    if divergence < MIN_DIVERGENCE_THRESHOLD:
        print(f"Signal Failed: Divergence from API consensus ({divergence:,.0f}) is below the {MIN_DIVERGENCE_THRESHOLD:,.0f} barrel threshold. No signal.")
        return

    # --- Generate Final Signal ---
    print("\n--- All Gating Rules Passed ---")
    if our_predicted_change > 0:
        signal = "BUILD"
        print(f"Final Signal: {signal} - Our model predicts a build of {our_predicted_change:,.0f} barrels, surprising the market.")
    else:
        signal = "DRAW"
        print(f"Final Signal: {signal} - Our model predicts a draw of {abs(our_predicted_change):,.0f} barrels, surprising the market.")

    return signal

if __name__ == '__main__':
    # This is a placeholder for running the script.
    EIA_API_KEY = "YOUR_KEY_HERE"

    # Create a dummy calibration file for testing
    if not os.path.exists('data'):
        os.makedirs('data')
    dummy_calibration = {
        "uncalibrated_volume": 65000000.0,
        "calibrated_volume": 68000000.0, # Our estimate for this week
        "eia_reported_volume": 68000000.0,
        "calibration_factor": 1.046
    }
    calibration_file = 'data/calibration_results.json'
    with open(calibration_file, 'w') as f:
        json.dump(dummy_calibration, f)

    generate_trading_signal(calibration_file, EIA_API_KEY)