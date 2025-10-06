import ee
import json
from datetime import datetime, timedelta

def download_cushing_data(days_ago=7):
    """
    Downloads Sentinel-1 and Sentinel-2 data for Cushing, OK.

    Args:
        days_ago (int): The number of days of data to download.
    """
    # Initialize Earth Engine
    try:
        ee.Initialize()
    except Exception:
        print("Please authenticate with Google Earth Engine first by running 'earthengine authenticate'")
        return

    # Define Cushing, OK bounding box and date range
    cushing_bbox = ee.Geometry.Rectangle([-96.9, 35.8, -96.7, 36.0])
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_ago)

    # --- Sentinel-2 Processing ---
    s2_collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterBounds(cushing_bbox) \
        .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))

    if s2_collection.size().getInfo() == 0:
        print("No suitable Sentinel-2 images found in the last", days_ago, "days.")
        s2_image = None
    else:
        s2_image = s2_collection.median()
        scl = s2_image.select('SCL')
        # Mask for clear pixels (vegetation, not vegetated, water, unclassified)
        mask = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6)).Or(scl.eq(7))
        s2_image = s2_image.updateMask(mask)

        # Scale to 0-255 uint8 for image processing
        s2_rgb = s2_image.select(['B4', 'B3', 'B2']) \
            .multiply(255 * 0.0001) \
            .uint8()

        # Get sun elevation metadata
        sun_elevation = s2_image.get('MEAN_SOLAR_ZENITH_ANGLE').getInfo()
        sun_elevation = 90 - sun_elevation if sun_elevation else 45

        # Export Sentinel-2 image
        task_s2 = ee.batch.Export.image.toDrive(
            image=s2_rgb,
            description=f'Cushing_S2_RGB_{end_date.strftime("%Y%m%d")}',
            folder='OilMonitoring',
            scale=10,
            region=cushing_bbox,
            maxPixels=1e9
        )
        task_s2.start()
        print("Started Sentinel-2 download task. Check Google Drive.")

    # --- Sentinel-1 Processing ---
    s1_collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
        .filterBounds(cushing_bbox) \
        .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
        .filter(ee.Filter.eq('instrumentMode', 'IW'))

    if s1_collection.size().getInfo() == 0:
        print("No suitable Sentinel-1 images found in the last", days_ago, "days.")
        s1_image = None
    else:
        s1_image = s1_collection.median()
        s1_vv = s1_image.select('VV')

        # Get incidence angle metadata
        incidence_angle = s1_image.get('MEAN_INCIDENCE_ANGLE_B1').getInfo()

        # Export Sentinel-1 image
        task_s1 = ee.batch.Export.image.toDrive(
            image=s1_vv,
            description=f'Cushing_S1_VV_{end_date.strftime("%Y%m%d")}',
            folder='OilMonitoring',
            scale=10,
            region=cushing_bbox,
            maxPixels=1e9
        )
        task_s1.start()
        print("Started Sentinel-1 download task. Check Google Drive.")

    # --- Metadata Export ---
    metadata = {
        's2_sun_elevation': sun_elevation if s2_image else None,
        's1_incidence_angle': incidence_angle if s1_image else None,
        'download_date': end_date.isoformat()
    }

    # This part is tricky as we can't write to a local file directly from here.
    # A better approach would be to save this to Google Drive as well.
    metadata_task = ee.batch.Export.table.toDrive(
        collection=ee.FeatureCollection([ee.Feature(None, metadata)]),
        description=f'Cushing_Metadata_{end_date.strftime("%Y%m%d")}',
        folder='OilMonitoring',
        fileFormat='JSON'
    )
    metadata_task.start()
    print("Started metadata export task. Check Google Drive.")

if __name__ == '__main__':
    download_cushing_data()