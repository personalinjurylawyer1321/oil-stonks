import ee
import geemap  # Optional: for interactive maps
from datetime import datetime, timedelta

# Initialize (run ee.Authenticate() first if needed)
ee.Initialize()

# Cushing geometry
cushing = ee.Geometry.Rectangle([-96.9, 35.8, -96.7, 36.0])

# Dates: Past week (adjust as needed)
start_date = '2025-09-28'
end_date = datetime.now().strftime('%Y-%m-%d')  # Today: 2025-10-05

# 1. Sentinel-2: RGB + Cloud Mask
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
    .filterBounds(cushing) \
    .filterDate(start_date, end_date) \
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
    .median()  # Median composite for clearest image
s2_rgb = s2.select(['B4', 'B3', 'B2']).divide(10000)  # Scale to 0-1
s2_cloudless = s2.updateMask(s2.select('SCL').eq(4))  # Mask clouds/land

# Export S2 RGB
task_s2 = ee.batch.Export.image.toDrive(
    image=s2_rgb,
    description='Cushing_S2_RGB_20250928_20251005',
    folder='OilMonitoring',
    scale=10,
    region=cushing,
    maxPixels=1e9
)
task_s2.start()

# 2. Landsat 8/9: RGB + Thermal for Proxies
l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2') \
    .filterBounds(cushing) \
    .filterDate(start_date, end_date) \
    .filter(ee.Filter.lt('CLOUD_COVER', 20)) \
    .median()
l8_rgb = l8.select(['SR_B4', 'SR_B3', 'SR_B2']).divide(10000).multiply(255).uint8()  # To 0-255
l8_thermal = l8.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15)  # Celsius

# Export Landsat RGB + Thermal
task_l8 = ee.batch.Export.image.toDrive(
    image=l8_rgb.addBands(l8_thermal),
    description='Cushing_L8_RGB_Thermal_20250928_20251005',
    folder='OilMonitoring',
    scale=30,
    region=cushing,
    maxPixels=1e9
)
task_l8.start()

# 3. MODIS: NDVI for Site Masking
modis = ee.ImageCollection('MODIS/006/MOD13Q1') \
    .filterBounds(cushing) \
    .filterDate(start_date, end_date) \
    .select('NDVI') \
    .median()
modis_ndvi = modis.multiply(0.0001)  # Scale to -1 to 1

# Export MODIS NDVI
task_modis = ee.batch.Export.image.toDrive(
    image=modis_ndvi,
    description='Cushing_MODIS_NDVI_20250928_20251005',
    folder='OilMonitoring',
    scale=250,
    region=cushing,
    maxPixels=1e9
)
task_modis.start()

# 4. Sentinel-1: VV Backscatter for SAR Height
s1 = ee.ImageCollection('COPERNICUS/S1_GRD') \
    .filterBounds(cushing) \
    .filterDate(start_date, end_date) \
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
    .filter(ee.Filter.eq('instrumentMode', 'IW')) \
    .select('VV') \
    .median() \
    .log10()  # Log scale for backscatter

# Export S1 VV
task_s1 = ee.batch.Export.image.toDrive(
    image=s1,
    description='Cushing_S1_VV_20250928_20251005',
    folder='OilMonitoring',
    scale=10,
    region=cushing,
    maxPixels=1e9
)
task_s1.start()

# 5. NISAR Placeholder: Early L/S-band (check Earthdata for exact ID post-late Oct)
# As of Oct 5, 2025, first images are available but not yet in GEE—use earthaccess for direct download.
# Placeholder query (uncomment when 'NISAR/L1_SLC' collection is live):
# nisar = ee.ImageCollection('NISAR/L1_SLC') \
#     .filterBounds(cushing) \
#     .filterDate('2025-09-25', end_date) \
#     .select('L_VV') \
#     .first()
# task_nisar = ee.batch.Export.image.toDrive(image=nisar, description='Cushing_NISAR_LVV', scale=10, region=cushing)
# task_nisar.start()

# Optional: Visualize in browser (uncomment)
# Map = geemap.Map(center=[35.9, -96.8], zoom=14)
# Map.addLayer(s2_rgb, {'min': 0, 'max': 0.3}, 'S2 RGB')
# Map.addLayer(s1, {'min': -25, 'max': 0}, 'S1 VV')
# Map.addLayer(cushing, {}, 'Cushing Bbox')
# Map  # This opens an interactive map

print("Tasks started—check Google Drive 'OilMonitoring' folder in ~10-30 min. Monitor status: ee.batch.Task.list()")
