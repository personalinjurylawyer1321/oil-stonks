import ee
import os
from datetime import datetime, timedelta
import json

def get_precipitation_flag(timestamp, aoi):
    """Checks for significant precipitation in the 24 hours prior to a timestamp."""
    try:
        acquisition_time = ee.Date(timestamp)
        start_time = acquisition_time.advance(-24, 'hour')

        # GPM IMERG: 30-min precipitation estimates
        precip_collection = ee.ImageCollection('NASA/GPM_L3/IMERG_V06') \
            .filterBounds(aoi) \
            .filterDate(start_time, acquisition_time) \
            .select('precipitationCal')

        # Check if collection is empty
        if precip_collection.size().getInfo() == 0:
            return False, 0.0

        # Sum precipitation over the 24-hour window
        total_precip = precip_collection.sum()

        # Get mean precipitation in the AOI (mm)
        precip_stat = total_precip.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=1000, # GPM resolution is ~10km
            maxPixels=1e9
        ).get('precipitationCal')

        # handle null value if there is no data
        precip_mm = precip_stat.getInfo() if precip_stat.getInfo() is not None else 0.0

        # Flag if more than 1mm of rain (adjust threshold as needed)
        is_wet = precip_mm > 1.0
        return is_wet, round(precip_mm, 2)
    except Exception as e:
        print(f"  - Warning: Could not fetch precipitation data. Error: {e}")
        return False, 0.0


def fetch_sentinel_data(start_date, end_date, output_dir='./data/raw'):
    """
    Fetches individual Sentinel-1 and Sentinel-2 scenes for the Cushing area
    and saves them with their metadata, including a weather flag.
    """
    # Initialize GEE
    try:
        ee.Initialize()
    except Exception:
        ee.Authenticate()
        ee.Initialize()

    # Define Cushing geometry
    cushing_aoi = ee.Geometry.Rectangle([-96.9, 35.8, -96.7, 36.0])
    os.makedirs(output_dir, exist_ok=True)
    print(f"Fetching data for AOI: {cushing_aoi.bounds().getInfo()}")
    print(f"Time range: {start_date} to {end_date}")

    # --- 1. Fetch Sentinel-2 L2A data ---
    s2_collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterBounds(cushing_aoi) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 25))

    s2_info = s2_collection.getInfo()['features']
    print(f"Found {len(s2_info)} suitable Sentinel-2 scenes.")

    for item in s2_info:
        image = ee.Image(item['id'])
        props = item['properties']
        scene_id = props['PRODUCT_ID']
        acq_timestamp = datetime.fromtimestamp(props['system:time_start'] / 1000)
        date_str = acq_timestamp.strftime('%Y%m%dT%H%M%S')

        print(f"\nProcessing S2 scene: {scene_id}")

        # Check for recent precipitation
        is_wet, precip_mm = get_precipitation_flag(acq_timestamp.isoformat(), cushing_aoi)
        print(f"  - Weather check: {precip_mm}mm rain in last 24h. Wet ground flag: {is_wet}")

        # Prepare metadata
        metadata = {
            'scene_id': scene_id,
            'timestamp': date_str,
            'cloud_cover': props.get('CLOUDY_PIXEL_PERCENTAGE'),
            'sun_azimuth': props.get('MEAN_SOLAR_AZIMUTH_ANGLE'),
            'sun_elevation': 90 - props.get('MEAN_SOLAR_ZENITH_ANGLE', 0),
            'precipitation_mm_24h': precip_mm,
            'is_wet_ground': is_wet,
        }

        # Export image
        filename_prefix = f"S2_{date_str}"
        filepath = os.path.join(output_dir, filename_prefix)

        task = ee.batch.Export.image.toCloudStorage(
            image=image.select(['B4', 'B3', 'B2', 'B8', 'SCL']), # RGB, NIR, SCL
            description=filename_prefix,
            bucket='your-gcs-bucket-name', # TODO: Replace with your GCS bucket
            fileNamePrefix=f'cushing_data/{filename_prefix}',
            scale=10,
            region=cushing_aoi,
            maxPixels=1e10,
            fileFormat='GeoTIFF'
        )
        # task.start() # Uncomment to run
        print(f"  - S2 Task (for GCS): {filename_prefix} (task not started)")

        # Save metadata locally
        with open(f"{filepath}.json", 'w') as f:
            json.dump(metadata, f, indent=4)
        print(f"  - Saved metadata: {filepath}.json")


    # --- 2. Fetch Sentinel-1 GRD data ---
    s1_collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
        .filterBounds(cushing_aoi) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.eq('instrumentMode', 'IW')) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', ['VV', 'VH']))

    s1_info = s1_collection.getInfo()['features']
    print(f"\nFound {len(s1_info)} suitable Sentinel-1 scenes.")

    for item in s1_info:
        props = item['properties']
        scene_id = props['system:index']
        acq_timestamp = datetime.fromtimestamp(props['system:time_start'] / 1000)
        date_str = acq_timestamp.strftime('%Y%m%dT%H%M%S')

        print(f"\nProcessing S1 scene: {scene_id}")

        # Check for recent precipitation
        is_wet, precip_mm = get_precipitation_flag(acq_timestamp.isoformat(), cushing_aoi)
        print(f"  - Weather check: {precip_mm}mm rain in last 24h. Wet ground flag: {is_wet}")

        # Prepare metadata
        metadata = {
            'scene_id': scene_id,
            'timestamp': date_str,
            'platform': props.get('platform_number'),
            'orbit_pass': props.get('orbitProperties_pass'),
            'incidence_angle_near': props.get('incidenceAngle_near'),
            'incidence_angle_far': props.get('incidenceAngle_far'),
            'precipitation_mm_24h': precip_mm,
            'is_wet_ground': is_wet,
        }

        filename_prefix = f"S1_{date_str}"
        filepath = os.path.join(output_dir, filename_prefix)

        print(f"  - Identified S1 scene for RTC processing queue.")

        # Save metadata locally to queue for HyP3 processing
        with open(f"{filepath}.json", 'w') as f:
            json.dump(metadata, f, indent=4)
        print(f"  - Saved metadata for HyP3 queue: {filepath}.json")

if __name__ == '__main__':
    # Set time range for the past month to get more scenes
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    fetch_sentinel_data(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    print("\nScript finished. Identified scenes and saved metadata.")
    print("Next steps: 1. Manually check GCS bucket for S2 images. 2. Run RTC script for S1 scenes.")
    print("NOTE: GEE export tasks were not started. Uncomment `task.start()` and configure GCS bucket to run.")