import os
from detection import detect_tanks  # Repo’s RetinaNet (retrain on S2 if needed)
from shadow_analysis import extract_shadow_height
from sar_height import compute_sar_height
from fusion import fuse_estimates

# Paths (from GEE exports; adjust filenames)
data_dir = './data'
s2_path = os.path.join(data_dir, 'Cushing_S2_RGB_20250928_20251005.tif')
l8_path = os.path.join(data_dir, 'Cushing_L8_RGB_Thermal_20250928_20251005.tif')
s1_path = os.path.join(data_dir, 'Cushing_S1_VV_20250928_20251005.tif')
modis_path = os.path.join(data_dir, 'Cushing_MODIS_NDVI_20250928_20251005.tif')
# nisar_path = ...  # Add when available

# Sun elevation: From S2 metadata (approx for Oct in OK: 40-50°)
sun_alpha = 45

# 1. Detect tanks on best optical (S2 preferred)
if os.path.exists(s2_path):
    detections = detect_tanks(s2_path)  # Returns bbox coords
    opt_path = s2_path
else:
    detections = detect_tanks(l8_path)
    opt_path = l8_path

# Crop to tanks if needed (simplified: assume full scene for prototype)

# 2. Extract heights
sar_heights, _ = compute_sar_height(s1_path)
opt_heights = extract_shadow_height(opt_path, l8_path if opt_path == s2_path else None, sun_alpha)

# 3. Fuse
estimates = fuse_estimates(sar_heights, opt_heights, modis_path)  # Add roof_clf=... later

# 4. Aggregate for Cushing total (~80M bbl capacity; scale by # tanks)
num_tanks = len(detections) if detections else 50  # From public: ~50 major tanks
total_volume = estimates['fused_volume'] * num_tanks if estimates else 0
print(f"Estimated Cushing Inventory: {total_volume:,.0f} barrels")

# Save: pd.DataFrame([estimates]).to_csv('cushing_estimate_20251005.csv')
