import random
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
    "hot": ["Hot"],
}
STATE_COMMENTS_DE: StateCommentMap = {
    "cold": ["Bibberkalt"],
    "perfect": ["Perfekt"],
    "warm": ["Es ist zu warm."],
    "hot": ["Höllenfeuer"],
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


@app.route("/")
def hello_world():
    entity = client.get_entity(entity_id="sensor.climate_living_room_temperature")
    if not entity:
        return "Temperatur konnte nicht geladen werden"

    locale, lang_code = negotiate_request_locale()
    temperature_state = entity.get_state()
    temperature_value: float = float(str(temperature_state.state))
    last_changed = temperature_state.last_changed

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

    return render_template(
        "index.html",
        comment=state_comment(temperature_value, lang_code),
        value=temperature_state.state,
        unit=temperature_state.attributes["unit_of_measurement"],
        updated=pretty_date(last_changed, locale),
        accent=temperature_accent(temperature_value),
        labels=labels,
        points=points,
        lang=locale.language,
    )
