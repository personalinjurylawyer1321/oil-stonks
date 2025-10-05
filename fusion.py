import rasterio
import numpy as np
from sklearn.ensemble import RandomForestClassifier  # For roof type (train once)

def fuse_estimates(sar_heights, optical_heights, modis_path, roof_clf=None):
    if sar_heights is None and optical_heights is None:
        return None

    # Weight: SAR-dominant (70%) for reliability; optical 30%
    if sar_heights and optical_heights:
        fused_h = 0.7 * sar_heights['height'] + 0.3 * optical_heights['height']
        fused_v = 0.7 * sar_heights['volume'] + 0.3 * optical_heights['volume']
    elif sar_heights:
        fused_h, fused_v = sar_heights['height'], sar_heights['volume']
    else:
        fused_h, fused_v = optical_heights['height'], optical_heights['volume']

    # MODIS mask: Industrial (low NDVI <0.2)
    with rasterio.open(modis_path) as src:
        ndvi = src.read(1)
    if np.mean(ndvi) > 0.2:  # Vegetated? Skip
        return None

    # Roof classification (if clf trained on backscatter/textures)
    if roof_clf:
        # Placeholder features: e.g., from SAR VV mean/var
        features = [np.mean(sar_heights.get('vv_mean', 0)), np.var(sar_heights.get('vv_var', 0))]
        roof_type = roof_clf.predict([features])[0]  # 0=fixed, 1=floating
        if roof_type == 0:  # Fixed: Impute historical avg
            fused_v = 500000  # Example: 0.5M bbl avg; load from CSV

    return {'fused_height': fused_h, 'fused_volume': fused_v, 'roof_type': roof_type if roof_clf else 'unknown'}

# Train clf once: From Airbus dataset (load in Jupyter)
# X_train = ... # Backscatter features
# y_train = ... # Labels
# roof_clf = RandomForestClassifier().fit(X_train, y_train)
