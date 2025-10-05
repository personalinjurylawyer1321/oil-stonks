from src.features.sar_double_bounce import annulus_azimuth_profile, arc_features
import numpy as np

def test_annulus_profile_peak_position():
    radius = 40
    H=W=2*radius+20
    cx=cy=H//2
    y,x = np.indices((H,W))
    dist2 = (x-cx)**2 + (y-cy)**2
    img = np.zeros((H,W), dtype="float32") + 0.2
    disk = dist2 <= radius**2
    img[~disk]=0

    r_in=int(radius*0.8); r_out=int(radius*1.05)
    theta = (np.degrees(np.arctan2(-(y-cy),(x-cx)))+360)%360
    arc_mask = (dist2>=r_in**2)&(dist2<=r_out**2)&(np.abs(((theta-90+180)%360)-180)<15)
    img[arc_mask]+=1.0

    prof = annulus_azimuth_profile(img,cx,cy,radius,0.7,1.1,360)
    feats = arc_features(prof)
    assert feats["peak_to_mean"] > 1.5
    assert feats["arc_width_deg"] > 10
