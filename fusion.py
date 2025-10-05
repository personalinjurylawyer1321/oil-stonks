import pandas as pd
import numpy as np

def fuse_per_tank_estimates(sar_results, optical_results, sar_weight=0.7):
    """
    Fuses per-tank estimates from SAR and optical analyses into a single best estimate.

    Args:
        sar_results (list of dict): The output from `sar_height.analyze_sar_for_tanks`.
        optical_results (list of dict): The output from `shadow_analysis.analyze_optical_for_tanks`.
        sar_weight (float): The weight to apply to the SAR estimate when both are available.
                            The optical weight will be (1 - sar_weight).

    Returns:
        pandas.DataFrame: A DataFrame with the fused estimates for each tank, including the
                          source of the final estimate.
    """
    if not sar_results and not optical_results:
        print("Warning: Both SAR and optical results are empty. No fusion possible.")
        return pd.DataFrame()

    # Convert results to DataFrames for easier merging
    sar_df = pd.DataFrame(sar_results).set_index('tank_id')
    optical_df = pd.DataFrame(optical_results).set_index('tank_id')

    # Rename columns to avoid clashes
    sar_df.rename(columns={'fill_volume_bbl': 'sar_volume_bbl', 'error': 'sar_error'}, inplace=True)
    optical_df.rename(columns={'fill_volume_bbl': 'optical_volume_bbl', 'error': 'optical_error'}, inplace=True)

    # Merge the two dataframes on the tank_id index
    fused_df = pd.concat([
        sar_df[['sar_volume_bbl', 'sar_error']],
        optical_df[['optical_volume_bbl', 'optical_error']]
    ], axis=1)

    # --- Fusion Logic ---
    fused_volume = []
    data_source = []

    for index, row in fused_df.iterrows():
        sar_vol = row.get('sar_volume_bbl')
        opt_vol = row.get('optical_volume_bbl')

        # Check if results are valid (not NaN or None)
        sar_valid = pd.notna(sar_vol)
        opt_valid = pd.notna(opt_vol)

        if sar_valid and opt_valid:
            # Both are valid: use a weighted average
            fused_vol = (sar_weight * sar_vol) + ((1 - sar_weight) * opt_vol)
            source = 'Fused (SAR/Optical)'
        elif sar_valid:
            # Only SAR is valid
            fused_vol = sar_vol
            source = 'SAR Only'
        elif opt_valid:
            # Only Optical is valid
            fused_vol = opt_vol
            source = 'Optical Only'
        else:
            # Neither is valid
            fused_vol = np.nan
            source = 'No Data'

        fused_volume.append(fused_vol)
        data_source.append(source)

    fused_df['fused_volume_bbl'] = fused_volume
    fused_df['data_source'] = data_source

    # Clean up and return
    return fused_df.reset_index()