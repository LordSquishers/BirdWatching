from typing import Tuple, List
import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
import requests

# this file was originally by me but i got hungry and tired
# and i REALLY did not want to deal with plotting libraries.
# i'm used to MATLAB and i would rather analyze the data than
# spend hours writing code to display it how i want
# so i used a bunch of gpt


def hour_to_ampm(h):  # better than AI ever could
    ampm_str = "PM" if h >= 12 else "AM"
    h = h % 12
    if h == 0: h = 12
    return f"{h} {ampm_str}"


EASTERN_TZ = "US/Eastern"
def fetch_weather_with_rain_intervals(
    lat: float,
    lon: float,
    start_timestamp: pd.Timestamp,
    end_timestamp: pd.Timestamp,
    rain_threshold_mm: float = 0.1
) -> Tuple[pd.DataFrame, List[Tuple[pd.Timestamp, pd.Timestamp]]]:
    """
    Fetch hourly precipitation and temperature from Open-Meteo, and compute rainy intervals.

    Returns:
        - df: pandas DataFrame with columns:
            - 'precipitation' (mm)
            - 'temperature' (°C)
          Index: hourly timestamps in US/Eastern
        - rainy_intervals: list of (start, end) tuples in US/Eastern
          representing continuous rainy periods (precipitation >= rain_threshold_mm)
    AI GENERATED AND ITS AWESOME
    """

    # Localize or convert timestamps to US/Eastern
    start_local = (
        start_timestamp.tz_localize(EASTERN_TZ)
        if start_timestamp.tzinfo is None
        else start_timestamp.tz_convert(EASTERN_TZ)
    )
    end_local = (
        end_timestamp.tz_localize(EASTERN_TZ)
        if end_timestamp.tzinfo is None
        else end_timestamp.tz_convert(EASTERN_TZ)
    )

    # Convert to UTC for API
    start_utc = start_local.tz_convert("UTC")
    end_utc = end_local.tz_convert("UTC")

    # Fetch data from Open-Meteo
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_utc.date().isoformat(),
        "end_date": end_utc.date().isoformat(),
        "hourly": "precipitation,temperature_2m",
        "timezone": "UTC"
    }

    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()

    # Build DataFrame in UTC
    times_utc = pd.to_datetime(data["hourly"]["time"], utc=True)
    df = pd.DataFrame({
        "precipitation": data["hourly"]["precipitation"],
        "temperature": data["hourly"]["temperature_2m"]
    }, index=times_utc)

    # Restrict to exact requested window
    df = df.loc[start_utc:end_utc]

    # Convert index to US/Eastern
    df.index = df.index.tz_convert(EASTERN_TZ)

    # Compute rainy intervals
    raining = df["precipitation"] >= rain_threshold_mm
    intervals = []
    interval_start = None

    for ts, is_raining in raining.items():
        if is_raining and interval_start is None:
            interval_start = ts
        elif not is_raining and interval_start is not None:
            intervals.append((interval_start, ts))
            interval_start = None

    # Close final interval
    if interval_start is not None:
        intervals.append((interval_start, df.index[-1] + pd.Timedelta(hours=1)))

    return df, intervals


# PARAMETERS (lat/long come w/ bird files but its not going to change very often)
LAT = 38.97
LONG = -77.25

PLOT_BIRD = True
PLOT_TEMP = True
PLOT_VOLTS = False

# summary file
audio_file_data = pd.read_csv("data/SUMMARY.csv", sep=',')

# birds
bird_data = pd.read_csv("data/bird_data.csv", sep=',', parse_dates=['Timestamp'])

# find total time elapsed between first and last recording
start_time = min(bird_data["Timestamp"])
end_time = max(bird_data["Timestamp"])

# print(bird_data.to_string())
if PLOT_BIRD:

    # assisted by gpt because i got lazy trying to write plotting code.
    bird_data["Hour"] = bird_data["Timestamp"].dt.hour
    table = (
        bird_data
        .groupby(["Bird_Species", "Hour"])
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
    # gpt saving me so much time here
    fig = plt.figure()
    ax = fig.gca()

    weather_df, rain_intervals = fetch_weather_with_rain_intervals(
        LAT, LONG, start_time, end_time
    )
    for s, e in rain_intervals:
        ax.axvspan(s, e, color="skyblue", alpha=0.2, label="Rain")

    ax.plot(weather_df.index, (9/5 * weather_df["temperature"]) + 32, label="Area", color="purple")
    plt.scatter(bird_data["Timestamp"], bird_data["Temperature"], s=0.4, label="Local")
    ax.set_ylabel("Temperature (°F)", color="purple")
    ax.tick_params(axis="y", labelcolor="purple")

    if PLOT_VOLTS:
        ax2 = ax.twinx()  # share x-axis
        plt.scatter(bird_data["Timestamp"], bird_data["Battery_Voltage"], s=0.4, label="Battery", color="red")
        ax2.set_ylabel("Battery (V)", color="red")
        ax2.tick_params(axis="y", labelcolor="red")
        ax2.set_ylim(bottom=0, top=4.3)

        # Optional: combine legends
        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines + lines2, labels + labels2)
    else:
        plt.legend()

    ax.set_xlabel("Time")
    plt.show()