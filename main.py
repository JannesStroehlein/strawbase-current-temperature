import random
import threading
import time
from typing import TypedDict
from zoneinfo import ZoneInfo
import datetime
import sys
import os
from flask import Flask, render_template, request
from babel import Locale, negotiate_locale
from babel.dates import format_date, format_timedelta
from homeassistant_api import Client, State

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


def negotiate_request_locale() -> tuple[Locale, str]:
    preferred = [lang.replace("-", "_") for lang, _ in request.accept_languages]
    matched = negotiate_locale(preferred, SUPPORTED_LOCALES)
    return Locale.parse(matched or "en_US"), matched or "en_US"


def pretty_date(d: datetime.datetime, locale: Locale) -> str:
    delta = d - datetime.datetime.now(tz=ZoneInfo("Europe/Berlin"))
    if abs(delta).days > 7:
        return format_date(d, locale=locale)
    return format_timedelta(delta, add_direction=True, locale=locale)


def temperature_accent(value: float) -> str:
    if value < 16:
        return "#60a5fa"
    elif value < 22:
        return "#34d399"
    elif value < 26:
        return "#fbbf24"
    else:
        return "#f87171"


class StateCommentMap(TypedDict):
    cold: list[str]
    perfect: list[str]
    warm: list[str]
    hot: list[str]


STATE_COMMENTS_ENG: StateCommentMap = {
    "cold": ["Freezing"],
    "perfect": ["Perfect"],
    "warm": ["Too hot"],
    "hot": [
        "Hot",
    ],
}
STATE_COMMENTS_DE: StateCommentMap = {
    "cold": ["Bibberkalt"],
    "perfect": ["Perfekt"],
    "warm": ["Es ist zu warm."],
    "hot": [
        "Höllenfeuer",
        "Warum ich?",
        "Wenn Dachgeschoss Wohnungen Öfen sind: Macht ein Ventilator dann Umluft?",
    ],
}


def state_comment(value: float, lang: str) -> str:
    comment_map = STATE_COMMENTS_DE if lang == "de_DE" else STATE_COMMENTS_ENG

    if value < 16:
        comment_pool = comment_map["cold"]
    elif value < 22:
        comment_pool = comment_map["perfect"]
    elif value < 26:
        comment_pool = comment_map["warm"]
    else:
        comment_pool = comment_map["hot"]

    comment = random.sample(comment_pool, 1)
    if comment and len(comment) == 1:
        return comment[0]
    return "Kommentarlos" if lang == "de_DE" else "- No comment -"


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
    global _cache, _cache_time
    with _cache_lock:
        if _cache is None or (time.monotonic() - _cache_time) >= CACHE_TTL_SECONDS:
            try:
                fresh = fetch_temperature_data()
            except Exception as exc:  # serve stale data on transient failures
                print(f"Failed to refresh HomeAssistant data: {exc}")
                fresh = None
            if fresh is not None:
                _cache = fresh
                _cache_time = time.monotonic()
        return _cache


@app.route("/")
def hello_world():
    data = get_temperature_data()
    if data is None:
        return "Temperatur konnte nicht geladen werden"

    locale, lang_code = negotiate_request_locale()
    return render_template(
        "index.html",
        comment=state_comment(data["value"], lang_code),
        value=data["state"],
        unit=data["unit"],
        updated=pretty_date(data["last_changed"], locale),
        accent=temperature_accent(data["value"]),
        labels=data["labels"],
        points=data["points"],
        lang=locale.language,
    )
