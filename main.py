import datetime
import os
import sys
import threading
import time
from typing import TypedDict
from zoneinfo import ZoneInfo

from babel import Locale, negotiate_locale
from babel.dates import format_date, format_timedelta
from flask import Flask, render_template, request
from homeassistant_api import Client, State

from temperature_classes import TemperatureClass

SUPPORTED_LOCALES = ["en_US", "de_DE"]

# Seconds before cached HomeAssistant data is considered stale and re-queried.
CACHE_TTL_SECONDS = float(os.getenv("CACHE_TTL_SECONDS", "30"))

# Number of days of personal history exposed by the weekly heatmap; 0 disables it.
HEATMAP_DAYS = max(0, int(os.getenv("HEATMAP_DAYS", "7")))

# Comfortable temperature band, shaded on the chart.
COMFORT_MIN = float(os.getenv("COMFORT_MIN", "16"))
COMFORT_MAX = float(os.getenv("COMFORT_MAX", "22"))

HASSIO_API_URL = os.getenv("HASSIO_API_URL")
HASSIO_API_TOKEN = os.getenv("HASSIO_API_TOKEN")
HASSIO_TEMPERATURE_SENSOR = os.getenv(
    "HASSIO_TEMPERATURE_SENSOR", "sensor.living_room_temperature"
)
HASSIO_TIMEZONE = ZoneInfo(os.getenv("HASSIO_TIMEZONE", "Europe/Berlin"))

client = Client(HASSIO_API_URL, HASSIO_API_TOKEN)

with client:
    if not client.check_api_running():
        print("Failed to connect to HomeAssistant API")
        sys.exit(1)
    app = Flask(__name__)


def state_with_unit_to_str(state: State) -> str:
    return f"{state.state} {state.attributes['unit_of_measurement']}"


def negotiate_request_locale() -> Locale:
    preferred = [lang.replace("-", "_") for lang, _ in request.accept_languages]
    matched = negotiate_locale(preferred, SUPPORTED_LOCALES)
    return Locale.parse(matched or "en_US")


def pretty_date(d: datetime.datetime, locale: Locale) -> str:
    delta = d - datetime.datetime.now(tz=HASSIO_TIMEZONE)
    if abs(delta).days > 7:
        return format_date(d, locale=locale)
    return format_timedelta(delta, add_direction=True, locale=locale)


class TemperatureData(TypedDict):
    value: float
    state: str
    unit: str
    last_changed: datetime.datetime
    labels: list[str]
    points: list[float]
    delta_24h: float | None
    today_min: float | None
    today_max: float | None
    today_avg: float | None
    heatmap: list[list[float | None]]
    heat_dates: list[datetime.date]
    heat_min: float | None
    heat_max: float | None


_cache_lock = threading.Lock()
_cache: TemperatureData | None = None
_cache_time: float = 0.0


def _build_heatmap(
    samples: list[tuple[datetime.datetime, float]], today: datetime.date
) -> tuple[list[list[float | None]], list[datetime.date], float | None, float | None]:
    """Bucket samples into a days x 24h grid of hourly averages."""
    start_date = today - datetime.timedelta(days=HEATMAP_DAYS - 1)
    dates = [start_date + datetime.timedelta(days=i) for i in range(HEATMAP_DAYS)]

    sums: dict[tuple[datetime.date, int], list[float]] = {}
    for ts, value in samples:
        if ts.date() < start_date:
            continue
        sums.setdefault((ts.date(), ts.hour), [0.0, 0.0])
        agg = sums[(ts.date(), ts.hour)]
        agg[0] += value
        agg[1] += 1

    grid: list[list[float | None]] = []
    values: list[float] = []
    for d in dates:
        row: list[float | None] = []
        for hour in range(24):
            agg = sums.get((d, hour))
            if agg:
                avg = agg[0] / agg[1]
                row.append(avg)
                values.append(avg)
            else:
                row.append(None)
        grid.append(row)

    return (
        grid,
        dates,
        (min(values) if values else None),
        (max(values) if values else None),
    )


def fetch_temperature_data() -> TemperatureData | None:
    """Query HomeAssistant for the current state plus history for chart and heatmap."""
    entity = client.get_entity(entity_id=HASSIO_TEMPERATURE_SENSOR)
    if not entity:
        return None

    temperature_state = entity.get_state()
    now = datetime.datetime.now(tz=HASSIO_TIMEZONE)
    day_cutoff = now - datetime.timedelta(hours=24)
    # Fetch enough history to cover both the 24h chart and the heatmap window.
    history_start = min(day_cutoff, now - datetime.timedelta(days=HEATMAP_DAYS))

    samples: list[tuple[datetime.datetime, float]] = []
    for history in client.get_entity_histories(
        entities=(entity,),
        start_timestamp=history_start,
        end_timestamp=now,
    ):
        for s in history.states:
            try:
                value = float(str(s.state))
            except ValueError:
                continue
            samples.append((s.last_changed.astimezone(HASSIO_TIMEZONE), value))

    samples.sort(key=lambda sv: sv[0])

    labels = [ts.strftime("%H:%M") for ts, _ in samples if ts >= day_cutoff]
    points = [value for ts, value in samples if ts >= day_cutoff]

    current = float(str(temperature_state.state))
    delta_24h: float | None = None
    if samples:
        # Value closest to 24h ago, accepted only when reasonably near the mark.
        ref_ts, ref_value = min(
            samples, key=lambda sv: abs((sv[0] - day_cutoff).total_seconds())
        )
        if abs((ref_ts - day_cutoff).total_seconds()) <= 3 * 3600:
            delta_24h = round(current - ref_value, 1)

    today_values = [value for ts, value in samples if ts.date() == now.date()]
    today_min = min(today_values) if today_values else None
    today_max = max(today_values) if today_values else None
    today_avg = (
        round(sum(today_values) / len(today_values), 1) if today_values else None
    )

    heatmap, heat_dates, heat_min, heat_max = _build_heatmap(samples, now.date())

    return TemperatureData(
        value=current,
        state=str(temperature_state.state),
        unit=temperature_state.attributes["unit_of_measurement"],
        last_changed=temperature_state.last_changed,
        labels=labels,
        points=points,
        delta_24h=delta_24h,
        today_min=today_min,
        today_max=today_max,
        today_avg=today_avg,
        heatmap=heatmap,
        heat_dates=heat_dates,
        heat_min=heat_min,
        heat_max=heat_max,
    )


def get_temperature_data() -> TemperatureData | None:
    """Return cached data, refreshing from HomeAssistant when older than the TTL."""
    global _cache, _cache_time  # pylint: disable=global-statement
    with _cache_lock:
        if _cache is None or (time.monotonic() - _cache_time) >= CACHE_TTL_SECONDS:
            try:
                fresh = fetch_temperature_data()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                print(f"Failed to refresh HomeAssistant data: {exc}")
                # serve stale data on transient failures
                fresh = None
            if fresh is not None:
                _cache = fresh
                _cache_time = time.monotonic()
        return _cache


@app.route("/")
def index():
    data = get_temperature_data()
    if data is None:
        return "Temperatur konnte nicht geladen werden"

    # TODO: Add heat wave shader effect
    locale = negotiate_request_locale()

    temp_class = TemperatureClass.for_temperature(data["value"])

    heat_labels = [
        format_date(d, format="EEE", locale=locale) for d in data["heat_dates"]
    ]

    return render_template(
        "index.html",
        comment=temp_class.pick_comment(locale),
        value=data["state"],
        unit=data["unit"],
        updated=pretty_date(data["last_changed"], locale),
        accent=temp_class.color,
        labels=data["labels"],
        points=data["points"],
        delta=data["delta_24h"],
        today_min=data["today_min"],
        today_max=data["today_max"],
        today_avg=data["today_avg"],
        comfort_min=COMFORT_MIN,
        comfort_max=COMFORT_MAX,
        heatmap=data["heatmap"],
        heat_labels=heat_labels,
        heat_min=data["heat_min"],
        heat_max=data["heat_max"],
        lang=locale.language,
    )


@app.route("/healthz")
def healthz():
    """Liveness/readiness probe: 200 when fresh HA data is available, else 503."""
    data = get_temperature_data()
    if data is None:
        return {"status": "unavailable"}, 503
    return {"status": "ok"}
