import os
import sys
from os.path import exists
from pathlib import Path
from zoneinfo import ZoneInfo

# this file is entirely written by me and with help from stack overflow

# silence command-line output temporarily (credit SO)
sys.stdout, sys.stderr = os.devnull, os.devnull

from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

# unsilence command-line output
sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__

import dateutil.parser
import pandas as pd

class SuppressedOutput:  # credit SO again. the birdnet library prints willy nilly
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout

# INIT #
ANALYSIS_TRACKER_FILEPATH = "analysis_tracker.txt"
SUMMARY_FILEPATH = "data/SUMMARY.csv"
ANALYSIS_DATA_FILEPATH = "data/bird_data.csv"

BIRD_RECORDINGS_DIR = "/Users/patrick/Desktop/creation/birds/recordings/"
BIRD_RECORDINGS_FILETYPE = "WAV"
BIRD_HEADERS = ["Bird_Species", "Timestamp", "Start_Offset", "Confidence", "Temperature", "Filename", "Battery_Voltage"]

LATITUDE = 38.97
LONGITUDE = -77.25

# load existing data
if exists(ANALYSIS_DATA_FILEPATH):
    bird_data = pd.read_csv(ANALYSIS_DATA_FILEPATH, sep=',')
    print(f"Loaded existing bird data from {ANALYSIS_DATA_FILEPATH} ({len(bird_data.index)} entries).")
else:
    bird_data = pd.DataFrame(columns=BIRD_HEADERS)
    print("No existing bird data found. Creating one now!")

# grab all the WAV files
pathlist = Path(BIRD_RECORDINGS_DIR).glob('**/*.' + BIRD_RECORDINGS_FILETYPE)

audio_file_dict = {}
for path in pathlist:
    path_str = str(path)
    audio_file_dict[path_str] = False
print(f"Found {len(audio_file_dict)} audio files.")

num_files = len(audio_file_dict)

num_analyzed = 0
actually_analyzed = 0 # sorry for this

# read files already analyzed
with open(ANALYSIS_TRACKER_FILEPATH, "r") as f:
    lines = f.readlines()
    for line in lines:
        line = line.strip("\n")
        if line in audio_file_dict.keys():
            audio_file_dict[line] = True
            num_analyzed += 1
print(f"{num_analyzed} audio files already analyzed.")

# load summary file for temperatures and voltages
# i decided to add voltages to the bird entries because i dont want to make
# a separate script to try and analyze them
print(f"Loading temperature/voltage data from {SUMMARY_FILEPATH}...")
summary_file_data = pd.read_csv(SUMMARY_FILEPATH, sep=',')

local_temp_data = {}
local_voltage_data = {}
for idx, row in summary_file_data.iterrows():  # code poached from old birdnet_gui_viewer.py
    # load timestamp from summary file
    timestamp = row['Timestamp']
    time = dateutil.parser.isoparse(timestamp).replace(tzinfo=ZoneInfo("America/New_York"))
    # the files before this time are in UTC and the ones after are in EST.
    # if you ever try to use the times to get the audio file path you'll need to adjust back
    if time < pd.Timestamp('2026-01-08 14:00:00', tz='America/New_York'):
        time -= pd.Timedelta(hours=5)
    # load temp from summary file and convert to fahrenheit
    temperature = (9/5 * row['Temperature (C)']) + 32
    local_temp_data[time] = temperature

    voltage = row['Battery Voltage (V)']
    local_voltage_data[time] = voltage

# load model
print("Loading model...")

with SuppressedOutput():
    analyzer = Analyzer()

total_analysis_time = pd.Timedelta(hours=0)
print("Starting analysis...")

for path in audio_file_dict.keys():
    # check if file is analyzed
    if audio_file_dict[path]:
        print(f"{path} already analyzed. Skipping!")
        continue

    start_analysis_time = pd.Timestamp.now()
    extracted_timestamp = dateutil.parser.isoparse(path.split("/")[-1].split(".")[0]).replace(tzinfo=ZoneInfo("America/New_York"))
    # the files before this time are in UTC and the ones after are in EST.
    # if you ever try to use the times to get the audio file path you'll need to adjust back
    if extracted_timestamp < pd.Timestamp('2026-01-08 14:00:00', tz='America/New_York'):
        extracted_timestamp -= pd.Timedelta(hours=5)

    # analyze file and save
    print(f"Analyzing {path}.")

    with SuppressedOutput():
        recording = Recording(
            analyzer,
            path,
            lat=LATITUDE,
            lon=LONGITUDE,
            # date=extracted_timestamp, causing analyzer to throw out native birds in "wrong time of year"
            # tell that to the bird in my backyard
            min_conf=0.65,
            return_all_detections=True
        )
        recording.analyze()

    actually_analyzed += 1
    num_analyzed += 1

    # learned that the model outputs a single detection per 3 seconds, so total detections can
    # be treated as total time bird is active

    # "Engine" is a valid output, im told as is human verbal and nonverbal

    # save data
    detections = recording.detections

    # current headers: "Bird_Species", "Timestamp", "Start_Offset", "Confidence", "Temperature", "Filename"
    for detection in detections:
        if detection["common_name"] == "Engine":
            detection["common_name"] = "Airplane" # it is almost ALWAYS a plane to/from DCA. that's just a larger bird
        elif not detection["is_predicted_for_location_and_date"]:
            print(f"\tDetection {detection['common_name']} not predicted for location and date. Skipping!")
            continue
        detection_entry = [detection["common_name"], extracted_timestamp, detection["start_time"], detection["confidence"], local_temp_data[extracted_timestamp], path, local_voltage_data[extracted_timestamp]]
        bird_data.loc[len(bird_data)] = detection_entry

    # mark analyzed
    audio_file_dict[path] = True

    # progress calculation
    end_analysis_time = pd.Timestamp.now()
    analysis_time = end_analysis_time - start_analysis_time
    total_analysis_time += analysis_time

    est_time = (total_analysis_time.total_seconds() / actually_analyzed) * (num_files - num_analyzed) # this is wrong
    est_time_minutes = int(est_time / 60)
    est_time_seconds = int(est_time % 60)

    print(f"Analysis of {path} took {round(analysis_time.total_seconds(),1)}s. Est. time remaining: {est_time_minutes}m{est_time_seconds}s. ({num_analyzed}/{num_files})")

# example output of detections array entry:
# {
# 'common_name': 'Carolina Wren',
# 'confidence': 0.9955547451972961,
# 'end_time': 3.0,
# 'label': 'Thryothorus ludovicianus_Carolina Wren',
# 'scientific_name': 'Thryothorus ludovicianus',
# 'start_time': 0.0,
# 'is_predicted_for_location_and_date': True
# }

# save bird data to csv
bird_data.to_csv(ANALYSIS_DATA_FILEPATH, index=False)
print(f"Saved bird data to {ANALYSIS_DATA_FILEPATH}.")

# save a list of detections already completed so they dont happen again
with open(ANALYSIS_TRACKER_FILEPATH, "w") as f:
    for key in audio_file_dict.keys():
        f.write(key + "\n")
print(f"Saved processed file list to {ANALYSIS_TRACKER_FILEPATH}.")
