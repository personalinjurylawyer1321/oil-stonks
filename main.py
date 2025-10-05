import os
import glob
from datetime import datetime
import pandas as pd

# Import the new, refactored analysis and fusion functions
from sar_height import analyze_sar_for_tanks
from shadow_analysis import analyze_optical_for_tanks
from fusion import fuse_per_tank_estimates

# --- Configuration ---
INVENTORY_FILE = './data/inventory/cushing_tank_inventory.csv'
RAW_DATA_DIR = './data/raw'
PROCESSED_SAR_DIR = './data/processed/s1_rtc'
RESULTS_DIR = './data/results'

def find_latest_file(directory, pattern):
    """Finds the most recent file in a directory matching a pattern."""
    files = glob.glob(os.path.join(directory, pattern))
    if not files:
        return None
    latest_file = max(files, key=os.path.getctime)
    return latest_file

def run_cushing_analysis():
    """
    Runs the full analysis pipeline: SAR, Optical, and Fusion.
    """
    print("--- Starting Cushing Oil Inventory Analysis ---")
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # 1. Find the latest available data files
    # For SAR, we use the processed RTC data (_VV.tif is the key band)
    latest_sar_file = find_latest_file(PROCESSED_SAR_DIR, '*_VV.tif')
    # For Optical, we use the raw S2 data (which our script reads)
    latest_optical_file = find_latest_file(RAW_DATA_DIR, 'S2_*.tif')

    if not latest_sar_file:
        print("Warning: No processed SAR file found. Skipping SAR analysis.")
        sar_results = []
    else:
        # 2. Run SAR Analysis
        sar_results = analyze_sar_for_tanks(latest_sar_file, INVENTORY_FILE)

    if not latest_optical_file:
        print("Warning: No optical file found. Skipping optical analysis.")
        optical_results = []
    else:
        # 3. Run Optical Shadow Analysis
        optical_results = analyze_optical_for_tanks(latest_optical_file, INVENTORY_FILE)

    # 4. Fuse the results
    print("\n--- Fusing SAR and Optical Estimates ---")
    fused_estimates_df = fuse_per_tank_estimates(sar_results, optical_results)

    if fused_estimates_df.empty:
        print("\nFusion resulted in no data. Cannot generate final report.")
        return

    # 5. Aggregate and report total volume
    final_report = fused_estimates_df.dropna(subset=['fused_volume_bbl'])
    total_cushing_volume = final_report['fused_volume_bbl'].sum()

    print("\n--- Final Cushing Inventory Estimate ---")
    print(f"Total Estimated Volume: {total_cushing_volume:,.0f} barrels")
    print(f"Number of tanks in estimate: {len(final_report)} / {len(fused_estimates_df)}")
    print("\nBreakdown by data source:")
    print(final_report['data_source'].value_counts())

    # 6. Save the detailed final report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_filename = os.path.join(RESULTS_DIR, f'cushing_inventory_report_{timestamp}.csv')
    final_report.to_csv(report_filename, index=False)
    print(f"\nDetailed report saved to: {report_filename}")


if __name__ == '__main__':
    # Before running, ensure dummy data exists from previous steps.
    # We need:
    # - ./data/inventory/cushing_tank_inventory.csv
    # - A dummy SAR RTC file in ./data/processed/s1_rtc/
    # - A dummy S1 metadata json in ./data/raw/
    # - A dummy S2 optical tif in ./data/raw/
    # - A dummy S2 metadata json in ./data/raw/

    run_cushing_analysis()