import os
import json
import time
import hyp3_sdk as sdk
from datetime import datetime

def process_s1_with_hyp3(data_dir='./data/raw', output_dir='./data/processed/s1_rtc'):
    """
    Submits Sentinel-1 GRD scenes for RTC processing via HyP3 and downloads results.
    """
    os.makedirs(output_dir, exist_ok=True)

    # --- Authenticate with HyP3 ---
    # NOTE: Requires NASA Earthdata login credentials stored as env vars
    # `EARTHDATA_LOGIN_USER` and `EARTHDATA_LOGIN_PASSWORD`
    try:
        user = os.environ.get('EARTHDATA_LOGIN_USER')
        password = os.environ.get('EARTHDATA_LOGIN_PASSWORD')
        hyp3 = sdk.HyP3(username=user, password=password, prompt=True)
    except Exception as e:
        print(f"HyP3 authentication failed. Ensure EARTHDATA_LOGIN_USER and EARTHDATA_LOGIN_PASSWORD are set.")
        print(f"Error: {e}")
        return

    print("Successfully authenticated with HyP3.")

    # --- Find S1 metadata files to process ---
    s1_files = [f for f in os.listdir(data_dir) if f.startswith('S1_') and f.endswith('.json')]
    if not s1_files:
        print("No S1 metadata files found to process. Run `fetch_cushing.py` first.")
        return

    # --- Submit RTC Jobs ---
    job_queue = []
    for meta_file in s1_files:
        with open(os.path.join(data_dir, meta_file), 'r') as f:
            metadata = json.load(f)

        scene_id = metadata['scene_id']
        job_name = f"rtc_{scene_id}"

        # Check if job already submitted or completed
        # Simple check: look for output file. A more robust check would query HyP3.
        output_filename_check = f"{job_name}_VV.tif"
        if os.path.exists(os.path.join(output_dir, output_filename_check)):
            print(f"Skipping {scene_id} - output seems to exist already.")
            continue

        print(f"Submitting RTC job for {scene_id}...")
        try:
            # Define RTC parameters
            rtc_job = hyp3.submit_rtc_job(
                granule=scene_id,
                name=job_name,
                dem_matching=True,
                include_dem=True,
                include_inc_map=True,
                radiometry='gamma-0', # Gamma-nought for stable backscatter
                scale='power',
                resolution=10,
                speckle_filter=True, # Apply a speckle filter
            )
            job_queue.append(rtc_job)
            print(f"  - Submitted as job: {rtc_job.job_id}")
        except Exception as e:
            print(f"  - Failed to submit job for {scene_id}. Error: {e}")

    if not job_queue:
        print("\nNo new jobs were submitted.")
        return

    # --- Monitor and Download Jobs ---
    print(f"\nWatching {len(job_queue)} jobs... (This can take 20-60 minutes)")

    # Refresh jobs from server to get latest status
    job_queue = hyp3.watch(job_queue)

    print("\nAll jobs have completed. Downloading results...")
    for job in job_queue:
        if job.succeeded():
            print(f"Downloading files for job: {job.job_id} ({job.files[0]['filename']})")
            try:
                job.download_files(output_dir)
                print(f"  - Successfully downloaded to: {output_dir}")
            except Exception as e:
                print(f"  - Download failed. Error: {e}")
        else:
            print(f"Job {job.job_id} failed. Check logs on ASF Vertex for details.")


if __name__ == '__main__':
    print("Starting Sentinel-1 RTC processing pipeline.")
    print("This script will submit jobs to ASF HyP3 and download the results.")
    print("Make sure your Earthdata Login credentials are set as environment variables.\n")

    process_s1_with_hyp3()

    print("\nRTC processing script finished.")