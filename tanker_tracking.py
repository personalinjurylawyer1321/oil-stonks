import pandas as pd
from shapely.geometry import Point, shape
from datetime import datetime, timedelta
import os

# --- Configuration ---
# Bounding boxes for major US crude oil ports/regions
# Format: [min_lon, min_lat, max_lon, max_lat]
PORT_ZONES = {
    "Houston": [-95.3, 29.5, -94.8, 29.8],
    "Corpus_Christi": [-97.5, 27.6, -97.2, 27.9],
    "Beaumont_Port_Arthur": [-94.2, 29.6, -93.7, 30.1],
    "LOOP_Offshore": [-90.5, 28.5, -89.5, 29.5], # Louisiana Offshore Oil Port
    "Delaware_Bay": [-75.6, 38.8, -74.9, 39.5]
}

# AIS vessel types for tankers (as per standard)
# https://www.navcen.uscg.gov/ais-ship-types
TANKER_AIS_TYPES = list(range(80, 90))

def load_ais_data(filepath):
    """Loads AIS data from a CSV file, ignoring commented lines."""
    try:
        # Explicitly set the comment character to handle the dummy data format
        df = pd.read_csv(filepath, parse_dates=['timestamp'], comment='#')
        print(f"Loaded {len(df)} AIS records from {os.path.basename(filepath)}")
        return df
    except FileNotFoundError:
        print(f"Error: AIS data file not found at {filepath}")
        return None

def filter_for_tankers(ais_df):
    """Filters the AIS DataFrame for tanker vessel types."""
    tanker_df = ais_df[ais_df['ship_type'].isin(TANKER_AIS_TYPES)].copy()
    print(f"Filtered down to {len(tanker_df)} tanker records.")
    return tanker_df

def assign_port_zone(ais_df, zones):
    """Assigns each AIS point to a defined port zone."""
    ais_df['geometry'] = ais_df.apply(lambda row: Point(row['lon'], row['lat']), axis=1)

    # Create shapely polygons for each zone
    zone_polygons = {name: shape({
        "type": "Polygon",
        "coordinates": [[
            [bbox[0], bbox[1]], [bbox[2], bbox[1]],
            [bbox[2], bbox[3]], [bbox[0], bbox[3]],
            [bbox[0], bbox[1]]
        ]]
    }) for name, bbox in zones.items()}

    def find_zone(point):
        for name, poly in zone_polygons.items():
            if poly.contains(point):
                return name
        return None

    ais_df['port_zone'] = ais_df['geometry'].apply(find_zone)
    return ais_df

def analyze_port_activity(tanker_df, start_date, end_date):
    """Analyzes tanker activity to identify port calls, arrivals, and departures."""
    # Filter for the analysis week
    week_df = tanker_df[(tanker_df['timestamp'] >= start_date) & (tanker_df['timestamp'] < end_date)].copy()

    # A 'port call' is defined as a vessel being inside a zone at any point during the week
    port_calls = week_df.dropna(subset=['port_zone']).groupby('port_zone')['mmsi'].nunique()

    # Simple arrival/departure logic:
    # An arrival is the first time a ship enters a zone this week.
    # A departure is the last time a ship is seen in a zone this week.
    week_df['date'] = week_df['timestamp'].dt.date

    arrivals = week_df.sort_values('timestamp').drop_duplicates(subset=['mmsi', 'port_zone'], keep='first')
    departures = week_df.sort_values('timestamp').drop_duplicates(subset=['mmsi', 'port_zone'], keep='last')

    arrival_counts = arrivals.groupby('port_zone')['mmsi'].count()
    departure_counts = departures.groupby('port_zone')['mmsi'].count()

    # Combine into a summary report
    summary = pd.DataFrame({
        'port_calls': port_calls,
        'arrivals': arrival_counts,
        'departures': departure_counts
    }).fillna(0).astype(int)

    summary.index.name = 'port_zone'
    return summary.reset_index()

def generate_tanker_report(ais_filepath, week_ending_date):
    """
    Main function to generate a weekly tanker activity report.
    """
    print(f"\nGenerating tanker report for week ending {week_ending_date.strftime('%Y-%m-%d')}...")
    end_date = week_ending_date
    start_date = end_date - timedelta(days=7)

    # 1. Load and filter data
    ais_df = load_ais_data(ais_filepath)
    if ais_df is None:
        return None

    tanker_df = filter_for_tankers(ais_df)

    # 2. Assign zones
    tanker_df_zoned = assign_port_zone(tanker_df, PORT_ZONES)

    # 3. Analyze activity for the week
    report = analyze_port_activity(tanker_df_zoned, start_date, end_date)

    return report

if __name__ == '__main__':
    # --- Example Usage with Dummy Data ---
    # This block allows the script to be run for testing purposes.

    dummy_ais_file = './data/ais/dummy_ais_data.csv'

    if not os.path.exists(dummy_ais_file):
        print(f"Error: Dummy AIS data file not found at '{dummy_ais_file}'.")
        print("Please create it first.")
    else:
        # Generate a report for the most recent week
        report_date = datetime.now()
        weekly_report = generate_tanker_report(dummy_ais_file, report_date)

        if weekly_report is not None:
            output_dir = './data/results'
            os.makedirs(output_dir, exist_ok=True)
            report_filename = os.path.join(output_dir, f"tanker_activity_report_{report_date.strftime('%Y%m%d')}.csv")
            weekly_report.to_csv(report_filename, index=False)

            print(f"\nSuccessfully generated tanker activity report.")
            print(weekly_report.to_string())
            print(f"\nSaved to: {report_filename}")