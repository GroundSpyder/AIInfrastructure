# Orthos Blackflame Dashboard For Birdmug

This is an alternate themed copy of the Orthos read-only dashboard for Kyle. It keeps the same read-only API behavior and uses a black, charcoal, grey, red, orange, and yellow palette inspired by Orthos, the Blackflame sacred turtle from Cradle.

It shows current request state, recent Orthos traffic, queue status, counters, generation speed, token summaries, and a one-button Orthos test. It does not include start/stop controls, allow/block controls, local Roo/Tabby activity, prompts, responses, process IDs, local paths, or token display.

## Requirements

- Birdmug must be able to reach Chris's Orthos URL over Tailscale.
- Chris's Orthos proxy must include the read-only endpoint:

```text
GET /v1/orthos/status
```

- Kyle needs the Orthos bearer token in `ORTHOS_API_TOKEN`. Do not save the token in this repo.

## Start

Set the Orthos token in the same terminal, then start the dashboard:

```bat
cd /d C:\LLM\orthos-blackflame-dashboard
set "ORTHOS_API_TOKEN=your-token-here"
start-orthos-readonly-dashboard.bat
```

Default URL:

```text
http://127.0.0.1:8792
```

Default Orthos upstream:

```text
https://chris13600k.tail406192.ts.net/v1
```

Optional settings:

```bat
set "ORTHOS_BASE_URL=https://chris13600k.tail406192.ts.net/v1"
set "LISTEN_HOST=127.0.0.1"
set "LISTEN_PORT=8792"
set "ORTHOS_TEST_MODEL=Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6"
```

## Status Meanings

- `Ready`: Orthos is available and no request is currently in flight.
- `Busy / Queued`: a generation is running or a request is queued.
- `Blocked`: Chris has disabled Kyle access.
- `Degraded`: recent queue timeout or upstream error activity was seen.
- `Down`: the dashboard cannot reach Orthos.

## Test Button

The test button runs:

- `GET /v1/models`
- a tiny `POST /v1/chat/completions`

If Orthos is busy, the request should wait in the Orthos queue. If it times out, the dashboard shows the retry delay from Orthos.

## What This Dashboard Cannot Do

- It cannot start or stop TabbyAPI.
- It cannot start or stop Orthos.
- It cannot allow or block Kyle access.
- It cannot view Chris's local Roo/Tabby activity.
- It cannot display prompts or responses.

## Stop

```bat
cd /d C:\LLM\orthos-blackflame-dashboard
stop-orthos-readonly-dashboard.bat
```
