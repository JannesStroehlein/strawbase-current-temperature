from zoneinfo import ZoneInfo
import datetime
import sys
import os
from flask import Flask, render_template
from homeassistant_api import Client, State

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


def pretty_date(d: datetime.datetime):
    diff = datetime.datetime.now(tz=ZoneInfo("Europe/Berlin")) - d
    s = diff.seconds
    if diff.days > 7 or diff.days < 0:
        return d.strftime("%d %b %y")
    elif diff.days == 1:
        return "1 day ago"
    elif diff.days > 1:
        return f"{diff.days} days ago"
    elif s <= 1:
        return "just now"
    elif s < 60:
        return f"{s} seconds ago"
    elif s < 120:
        return "1 minute ago"
    elif s < 3600:
        return f"{round(s / 60)} minutes ago"
    elif s < 7200:
        return "1 hour ago"
    else:
        return f"{round(s / 3600)} hours ago"


def temperature_accent(value: float) -> str:
    if value < 16:
        return "#60a5fa"
    elif value < 22:
        return "#34d399"
    elif value < 26:
        return "#fbbf24"
    else:
        return "#f87171"


@app.route("/")
def hello_world():
    entity = client.get_entity(entity_id="sensor.climate_living_room_temperature")
    if not entity:
        return "Temperatur konnte nicht geladen werden"

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
        value=temperature_state.state,
        unit=temperature_state.attributes["unit_of_measurement"],
        updated=pretty_date(last_changed),
        accent=temperature_accent(temperature_value),
        labels=labels,
        points=points,
    )
