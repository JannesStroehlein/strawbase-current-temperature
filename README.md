# strawbase-current-temperature

Small Flask site showing the current living-room temperature from Home Assistant,
with a localized "last updated" label, a state comment, a 24h history chart
(Chart.js, vendored locally) with a shaded comfort band, today's min/avg/max,
a change-vs-24h-ago delta, and a GitHub-style heatmap of hourly averages over
the last few days.

A `/healthz` endpoint returns `200` when fresh Home Assistant data is available
(`503` otherwise) for container liveness/readiness probes.

## Environment variables

| Variable                    | Required | Default                          | Description                                                       |
| --------------------------- | -------- | -------------------------------- | ----------------------------------------------------------------- |
| `HASSIO_API_URL`            | yes      | —                                | Home Assistant REST API base URL, e.g. `http://ha.local:8123/api` |
| `HASSIO_API_TOKEN`          | yes      | —                                | Long-lived access token for the Home Assistant API                |
| `HASSIO_TIMEZONE`           | no       | `Europe/Berlin`                  | Timezone of the Home Assistant instance.                          |
| `HASSIO_TEMPERATURE_SENSOR` | no       | `sensor.living_room_temperature` | Sensor for the living room temperature.                           |
| `CACHE_TTL_SECONDS`         | no       | `30`                             | Seconds before cached Home Assistant data is re-queried           |
| `HEATMAP_DAYS`              | no       | `7`                              | Days of personal history exposed by the weekly heatmap; `0` hides it |
| `COMFORT_MIN`               | no       | `16`                             | Lower bound of the comfort band shaded on the chart (°)           |
| `COMFORT_MAX`               | no       | `22`                             | Upper bound of the comfort band shaded on the chart (°)           |

Copy `.env.example` to `.env` and fill in your values. `.env` is gitignored —
never commit your token.

## Run locally

```sh
uv run flask --app main run
```

## Run with Docker

```sh
docker build -t strawbase-temp .
docker run -p 8000:8000 \
  -e HASSIO_API_URL=http://ha.local:8123/api \
  -e HASSIO_API_TOKEN=your-long-lived-token \
  -e CACHE_TTL_SECONDS=30 \
  strawbase-temp
```

The app validates the Home Assistant connection on startup and exits if it
cannot reach the API, so the env vars must be set before launch.
