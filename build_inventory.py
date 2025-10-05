import os
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, box
from owslib.wms import WebMapService
import numpy as np
from skimage.transform import hough_circle, hough_circle_peaks
from skimage.feature import canny
from skimage.draw import circle_perimeter
from skimage.color import rgb2gray
import rasterio
from rasterio.mask import mask
from io import BytesIO

# --- Configuration ---
CUSHING_BBOX = [-96.9, 35.8, -96.7, 36.0]  # Expanded BBox for Cushing tank farms
OUTPUT_DIR = './data/inventory'
OUTPUT_CSV = os.path.join(OUTPUT_DIR, 'cushing_tank_inventory.csv')
NAIP_WMS_URL = 'https://imagery.nationalmap.gov/arcgis/services/USGSNAIPPlus/ImageServer/WMSServer'

def fetch_osm_tanks(bbox):
    """Queries OpenStreetMap for storage tanks within a bounding box."""
    print("Querying OpenStreetMap for initial tank locations...")
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["man_made"="storage_tank"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
      way["man_made"="storage_tank"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
      relation["man_made"="storage_tank"]({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
    );
    out center;
    """
    try:
        response = requests.get(overpass_url, params={'data': query})
        response.raise_for_status()
        data = response.json()

        tanks = []
        for element in data['elements']:
            if 'type' in element and 'lat' in element and 'lon' in element:
                tanks.append({
                    'osm_id': element['id'],
                    'latitude': element['lat'],
                    'longitude': element['lon'],
                    'geometry': Point(element['lon'], element['lat'])
                })

        if not tanks:
            print("Found 0 potential tanks in OSM.")
            return gpd.GeoDataFrame(
                {'osm_id': [], 'latitude': [], 'longitude': [], 'geometry': []},
                geometry='geometry',
                crs="EPSG:4326"
            )

        df = pd.DataFrame(tanks)
        gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
        print(f"Found {len(gdf)} potential tanks in OSM.")
        return gdf
    except requests.exceptions.RequestException as e:
        print(f"Error querying Overpass API: {e}")
        return None

def get_naip_imagery_for_tank(tank_geom, buffer_m=100):
    """Fetches a high-resolution NAIP image chip around a single tank."""
    try:
        # Connect to the NAIP WMS server
        wms = WebMapService(NAIP_WMS_URL, version='1.3.0')
        # Dynamically get the first (and likely only) layer name
        layer_name = list(wms.contents)[0]
    except Exception as e:
        print(f"  - Could not connect to WMS or get layer list. Error: {e}")
        return None, None

    # Create a GeoSeries to handle the CRS transformation
    geo_series = gpd.GeoSeries([tank_geom], crs="EPSG:4326")

    # Define a bounding box around the tank in the correct projection
    tank_utm = geo_series.to_crs(epsg=32614) # Project to UTM zone 14N
    bounds_df = tank_utm.buffer(buffer_m).bounds
    bbox_tuple = (bounds_df.minx[0], bounds_df.miny[0], bounds_df.maxx[0], bounds_df.maxy[0])

    # Get the image from the WMS
    try:
        print(f"  - Requesting NAIP from layer '{layer_name}'...")
        img = wms.getmap(
            layers=[layer_name],
            styles=['default'],
            srs='EPSG:32614',
            bbox=bbox_tuple,
            size=(512, 512), # Request a 512x512 pixel image
            format='image/tiff',
            transparent=False
        )
        return img.read(), bbox_tuple
    except Exception as e:
        print(f"  - Could not fetch NAIP image for tank. Error: {e}")
        return None, None

def measure_tank_diameter(image_data, image_bounds):
    """Measures tank diameter from a NAIP image chip using Circle Hough Transform."""
    if image_data is None:
        return None

    # Read image with rasterio to handle GeoTIFF format
    with BytesIO(image_data) as memfile:
        with rasterio.open(memfile) as dataset:
            image = dataset.read([1,2,3]) # Read RGB
            image = np.moveaxis(image, 0, -1) # HWC
            res = dataset.res[0] # Pixel resolution in meters
    print(f"    - Image resolution: {res:.2f} m/pixel")

    # Pre-process image - use 8-bit for canny
    gray_image = (rgb2gray(image) * 255).astype(np.uint8)
    # Relaxed Canny parameters
    edges = canny(gray_image, sigma=1.5, low_threshold=10, high_threshold=30)
    print(f"    - Found {np.count_nonzero(edges)} edge pixels.")

    # Detect circles using Hough Transform
    # Radii range: e.g., 15m to 80m diameter for large tanks -> 7.5m to 40m radius
    min_radius_m, max_radius_m = 7.5, 40
    min_radius_px = int(min_radius_m / res)
    max_radius_px = int(max_radius_m / res)
    print(f"    - Searching for radii between {min_radius_px} and {max_radius_px} pixels.")

    if min_radius_px >= max_radius_px:
        print("    - Invalid radius search range. Skipping.")
        return None

    hough_radii = np.arange(min_radius_px, max_radius_px, 1)
    hough_res = hough_circle(edges, hough_radii)

    # Find the most prominent circle
    accums, cx, cy, radii = hough_circle_peaks(hough_res, hough_radii,
                                               min_xdistance=5, min_ydistance=5,
                                               total_num_peaks=1, normalize=True)

    if len(radii) > 0:
        # Convert radius from pixels to meters
        diameter_m = radii[0] * 2 * res
        return round(diameter_m, 2)
    else:
        print("    - Hough transform found no circles.")
        return None

def build_inventory():
    """Main function to build and save the tank inventory."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Get initial locations from OpenStreetMap
    osm_tanks = fetch_osm_tanks(CUSHING_BBOX)
    if osm_tanks is None or osm_tanks.empty:
        print("Could not retrieve tank locations. Aborting.")
        return

    # 2. Iterate through tanks, get NAIP imagery, and measure diameter
    inventory = []
    for index, tank in osm_tanks.iterrows():
        print(f"\nProcessing tank {index + 1}/{len(osm_tanks)} (OSM ID: {tank['osm_id']})...")
        image_data, image_bounds = get_naip_imagery_for_tank(tank['geometry'])

        if image_data:
            diameter = measure_tank_diameter(image_data, image_bounds)
            if diameter:
                print(f"  - Measured Diameter: {diameter} m")
                inventory.append({
                    'tank_id': f"cushing_{index:04d}",
                    'osm_id': tank['osm_id'],
                    'latitude': tank['latitude'],
                    'longitude': tank['longitude'],
                    'diameter_m': diameter,
                    'roof_type': 'floating' # Assume floating for now; can be refined later
                })
            else:
                print("  - Could not measure diameter.")
        else:
            print("  - Failed to retrieve NAIP imagery.")

    # 3. Save to CSV
    if inventory:
        inventory_df = pd.DataFrame(inventory)
        inventory_df.to_csv(OUTPUT_CSV, index=False)
        print(f"\nSuccessfully built inventory with {len(inventory_df)} tanks.")
        print(f"Saved to: {OUTPUT_CSV}")
    else:
        print("\nNo tanks were successfully processed. Inventory not saved.")

if __name__ == '__main__':
    build_inventory()