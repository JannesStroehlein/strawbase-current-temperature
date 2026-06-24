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

HASSIO_API_URL = os.getenv("HASSIO_API_URL")
HASSIO_API_TOKEN = os.getenv("HASSIO_API_TOKEN")

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
    delta = d - datetime.datetime.now(tz=ZoneInfo("Europe/Berlin"))
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


_cache_lock = threading.Lock()
_cache: TemperatureData | None = None
_cache_time: float = 0.0


def fetch_temperature_data() -> TemperatureData | None:
    """Query HomeAssistant for the current state and 24h history."""
    entity = client.get_entity(entity_id="sensor.climate_living_room_temperature")
    if not entity:
        return None

    temperature_state = entity.get_state()
    now = datetime.datetime.now(tz=ZoneInfo("Europe/Berlin"))
    labels: list[str] = []
    points: list[float] = []
    for history in client.get_entity_histories(
        entities=(entity,),
        start_timestamp=now - datetime.timedelta(hours=24),
        end_timestamp=now,
    ):
        for s in history.states:
            try:
                points.append(float(str(s.state)))
            except ValueError:
                continue
            labels.append(
                s.last_changed.astimezone(ZoneInfo("Europe/Berlin")).strftime("%H:%M")
            )

    return TemperatureData(
        value=float(str(temperature_state.state)),
        state=str(temperature_state.state),
        unit=temperature_state.attributes["unit_of_measurement"],
        last_changed=temperature_state.last_changed,
        labels=labels,
        points=points,
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

    return render_template(
        "index.html",
        comment=temp_class.pick_comment(locale),
        value=data["state"],
        unit=data["unit"],
        updated=pretty_date(data["last_changed"], locale),
        accent=temp_class.color,
        labels=data["labels"],
        points=data["points"],
        lang=locale.language,
    )
