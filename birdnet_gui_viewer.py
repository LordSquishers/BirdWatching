from zoneinfo import ZoneInfo

import pandas as pd
import dateutil.parser
from matplotlib import pyplot as plt
import meteostat as ms
from datetime import timezone
import seaborn as sns

def hour_to_ampm(h):  # better than AI ever could
    ampm_str = "PM" if h >= 12 else "AM"
    h = h % 12
    if h == 0: h = 12
    return f"{h} {ampm_str}"

# PARAMETERS (lat/long come w/ bird files but its not going to change very often)
LAT = 38.97
LONG = -77.25

PLOT_BIRD = True
PLOT_TEMP = False

# summary file
audio_file_data = pd.read_csv("data/SUMMARY.csv", sep=',')

# load time and temp data from the summary csv created by audiomoth
time_data = []
temp_data = []

for idx, row in audio_file_data.iterrows():
    # load timestamp from summary file
    timestamp = row['Timestamp']
    time = dateutil.parser.isoparse(timestamp).astimezone(timezone.utc)

    # the files before this time are in UTC and the ones after are in EST.
    # if you ever try to use the times to get the audio file path you'll need to adjust back
    if time < pd.Timestamp('2026-01-08 14:00:00', tz='UTC'):
        time -= pd.Timedelta(hours=5)

    # load temp from summary file and convert to fahrenheit
    temperature = (9/5 * row['Temperature (C)']) + 32

    # TODO: load battery voltage to get an estimate of battery life

    # save to lists. could change to dataframe but i dont wanna change the code
    time_data.append(time)
    temp_data.append(temperature)

# total real time between first and last recording, not total recording time
time_elapsed = (time_data[-1] - time_data[0]).total_seconds() / 86400

# birds
bird_data = pd.DataFrame(columns=['Common Name', 'Time', 'Temperature'])
table_data = pd.read_csv("data/BirdNET_SelectionTable.txt", sep='\t')

# go through allll the birds
for selection_num in table_data['Selection']:
    idx = selection_num - 1
    species_name = table_data['Common Name'][idx]

    # get the timestamp from the path name
    audio_file_name = table_data['Begin Path'][idx].split("/")[-1]
    timestamp = dateutil.parser.parse(audio_file_name.split(".")[0], fuzzy=True).astimezone(ZoneInfo("America/New_York"))

    # same shenanigans as before
    if timestamp < pd.Timestamp('2026-01-08 16:00:00', tz='US/Eastern'):
        timestamp -= pd.Timedelta(hours=5)

    # get the temperature from the summary file using the timestamp from the bird selection table
    temp = audio_file_data.loc[audio_file_data["File Name"] == audio_file_name]["Temperature (C)"].iloc[0]
    temp = (temp * 9/5) + 32 # c to f

    # save the entry
    bird_data.loc[len(bird_data)] = [species_name, timestamp, temp]

# print(bird_data.to_string())
if PLOT_BIRD:

    # assisted by gpt because i got lazy trying to write plotting code.
    bird_data["Hour"] = bird_data["Time"].dt.tz_convert("US/Eastern").dt.hour
    table = (
        bird_data
        .groupby(["Common Name", "Hour"])
        .size()
        .unstack(fill_value=0)
    )

    table = table.reindex(columns=range(24), fill_value=0)
    table.columns = [hour_to_ampm(h) for h in table.columns]

    # table extras
    table = table.loc[table.sum(axis=1).sort_values(ascending=False).index]
    table = table.loc[:, table.sum(axis=0) > 0] # hides hours w/ no data

    table_norm = table.div(table.max(axis=1), axis=0)

    sns.heatmap(
        table_norm,
        cmap="viridis",
        linewidths=0.3,
        linecolor="gray",
        annot=table,
        fmt="d",
        cbar=False
    )

    ax = plt.gca()

    ax.set_yticks([i + 0.5 for i in range(len(table.index))])
    ax.set_yticklabels(table.index, rotation=0, va='center')

    plt.xlabel("Hour")
    plt.ylabel("Bird")
    plt.tight_layout()
    plt.show()
    # end AI

# temperature brought to you by TD Bank
if PLOT_TEMP:
    # pull actual temp data from dulles
    location = ms.Point(LAT, LONG, 110)
    station = ms.stations.nearby(location, limit=1)
    ts = ms.hourly(station, start=time_data[0], end=time_data[-1], timezone='UTC')
    df = (ts.fetch()[ms.Parameter.TEMP] * 9/5) + 32
    # for some reason i can't get meteostat to interpolate and i think
    # its because the stations are 11-16 miles away

    # compare local temp to the temp 11 miles away and pretend its similar
    fig = plt.figure()
    plt.plot(df.index.get_level_values('time'), df, color='red')
    plt.scatter(time_data, temp_data, s=0.4)
    plt.xlabel('Time')
    plt.ylabel('Temperature (F)')
    plt.legend(['Dulles Station', 'Local Temp'])
    plt.show()