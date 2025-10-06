# Oil Tank Volume Estimation and Trading Signal Generation

This project provides a Python-based pipeline for estimating crude oil storage volumes in Cushing, Oklahoma, using free satellite imagery from Sentinel-1 (SAR) and Sentinel-2 (optical). It then calibrates these estimates against weekly EIA data to generate a trading signal (build or draw).

This implementation is a complete rewrite of the original proof-of-concept, addressing critical bugs in data handling, algorithmic accuracy, and parameterization.

## Features

- **Automated Data Downloading:** Fetches recent Sentinel-1 and Sentinel-2 imagery for Cushing, OK using Google Earth Engine.
- **Correct Preprocessing:** Implements proper cloud masking for Sentinel-2 and consistent data scaling for all imagery.
- **Metadata Extraction:** Automatically extracts and saves critical metadata like sun elevation and SAR incidence angles.
- **Modular Analysis Pipeline:**
    - `download_data.py`: Handles all data acquisition.
    - `tank_detection.py`: Placeholder for a deep learning-based tank detector.
    - `calculate_shadow_height.py`: Calculates tank height from optical imagery using shadow analysis.
    - `calculate_sar_height.py`: Calculates tank height from SAR imagery using layover analysis.
    - `process_imagery.py`: Orchestrates the detection and height calculation workflow.
- **EIA Calibration:** Fuses estimates from both SAR and optical data and calibrates the total volume against the official weekly EIA report.
- **Signal Generation:** Applies user-defined gating rules to generate a final, high-confidence "BUILD" or "DRAW" signal.

## How to Run the Pipeline

### 1. Prerequisites

- Python 3.8+
- An active Google Earth Engine account. If you don't have one, sign up at [earthengine.google.com](https://earthengine.google.com/).
- An EIA API key. Get one for free from the [EIA website](https://www.eia.gov/opendata/register.php).

### 2. Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-name>
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: The `requirements.txt` file may need to be updated with `earthengine-api`, `pandas`, `requests`, `scikit-image`, `opencv-python`, and `rasterio`.*

3.  **Authenticate with Google Earth Engine:**
    Run the following command in your terminal and follow the on-screen instructions.
    ```bash
    earthengine authenticate
    ```

4.  **Add your EIA API Key:**
    Open the `fuse_and_calibrate.py` and `generate_signal.py` files and replace `"YOUR_KEY_HERE"` with your actual EIA API key.

### 3. Execution

The pipeline is designed to be run in sequence.

1.  **Download Data:**
    Run the `download_data.py` script. This will start download tasks in your Google Earth Engine account. The files (GeoTIFFs and a metadata JSON) will be saved to a folder named `OilMonitoring` in your Google Drive.
    ```bash
    python download_data.py
    ```
    You must wait for the tasks to complete and then **manually move the downloaded files** from your Google Drive `OilMonitoring` folder into a local `data/` directory.

2.  **Process Imagery:**
    Once the data is in the `data/` directory, run the main processing script. This script uses the placeholder tank detector and then calculates the volume for each tank using both SAR and shadow methods. The results are saved to `data/tank_volume_estimates.json`.
    ```bash
    python process_imagery.py
    ```

3.  **Fuse and Calibrate:**
    This script takes the per-tank estimates, fuses them, and calibrates the total volume against the latest EIA data. The output is saved to `data/calibration_results.json`.
    ```bash
    python fuse_and_calibrate.py
    ```

4.  **Generate Trading Signal:**
    Finally, run this script to apply the gating rules and generate the final trading signal based on the calibrated results.
    ```bash
    python generate_signal.py
    ```

## Important Notes

- **Tank Detection:** The current `tank_detection.py` uses a hardcoded list of bounding boxes. For accurate, real-world results, this should be replaced with a trained object detection model as outlined in the original `Oil-Tank-Volume-Estimation/` notebooks.
- **Data Directory:** The scripts assume that the downloaded data is located in a `./data/` directory. Ensure you create this directory and place the files there.
- **Error Handling:** The scripts include basic error handling but can be extended for more robust, production-level use.