# strawbase-current-temperature

Small Flask site showing the current living-room temperature from Home Assistant,
with a localized "last updated" label, a state comment, and a 24h history chart
(Chart.js, vendored locally).

## Environment variables

| Variable            | Required | Default | Description                                                       |
| ------------------- | -------- | ------- | ----------------------------------------------------------------- |
| `HASSIO_API_URL`    | yes      | —       | Home Assistant REST API base URL, e.g. `http://ha.local:8123/api` |
| `HASSIO_API_TOKEN`  | yes      | —       | Long-lived access token for the Home Assistant API                |
| `CACHE_TTL_SECONDS` | no       | `30`    | Seconds before cached Home Assistant data is re-queried           |

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
