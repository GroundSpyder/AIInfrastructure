# Orthos API

Orthos is the shared, authenticated OpenAI-compatible interface for Kyle's AI.
It exposes the shared Qwen coding model through a narrow proxy.

## Owner

Orthos is GroundSpyder/Chris's local API running on Chris's machine.

## Current Endpoints

Primary DNS-free endpoint for Kyle:

```text
http://100.114.166.24:8787/v1
```

MagicDNS endpoint, if Tailscale DNS works on Kyle's machine:

```text
https://chris13600k.tail406192.ts.net/v1
```

Use the DNS-free endpoint first if Kyle is seeing dead connections or DNS
resolution failures.

## Authentication

Orthos requires a bearer token on every request:

```http
Authorization: Bearer <ORTHOS_BEARER_TOKEN>
```

The token is also defined in:

```text
C:\LLM\start-tabby-auth-proxy.bat
```

Rotate it there if it is ever shared too broadly.

## Model

Kyle's AI should use this model id:

```text
Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6
```

Recommended client settings:

```text
API type: OpenAI-compatible
Base URL: http://100.114.166.24:8787/v1
API key:  <ORTHOS_BEARER_TOKEN>
Model:    Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6
```

## Supported Routes

The proxy intentionally allows only these routes:

```text
GET  /v1/models
POST /v1/chat/completions
POST /v1/completions
```

Other paths return `404`.

## Topology

DNS-free path:

```text
Kyle's AI
  -> http://100.114.166.24:8787/v1
  -> Tailscale Serve TCP on Chris machine
  -> 127.0.0.1:8787 auth proxy
  -> 127.0.0.1:8082 shared TabbyAPI
  -> Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6
```

MagicDNS HTTPS path:

```text
Kyle's AI
  -> https://chris13600k.tail406192.ts.net/v1
  -> Tailscale Serve HTTPS
  -> 127.0.0.1:8787 auth proxy
  -> 127.0.0.1:8082 shared TabbyAPI
```

## Local Services

Shared TabbyAPI:

```text
127.0.0.1:8082
```

Orthos auth proxy:

```text
127.0.0.1:8787
```

Tailscale Serve mappings:

```text
tcp://100.114.166.24:8787 -> tcp://127.0.0.1:8787
https://chris13600k.tail406192.ts.net/ -> http://127.0.0.1:8787
```

## Start And Stop

Start the Orthos auth proxy:

```powershell
C:\LLM\start-tabby-auth-proxy.bat
```

Stop the Orthos auth proxy:

```powershell
C:\LLM\stop-tabby-auth-proxy.bat
```

Reapply Tailscale Serve mappings:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\LLM\enable-tailscale-serve-tabby-proxy.ps1
```

The proxy timeout is configured for long generations:

```text
PROXY_TIMEOUT_SECONDS=3600
```

## Example Requests

List models:

```powershell
Invoke-RestMethod `
  -Uri 'http://100.114.166.24:8787/v1/models' `
  -Headers @{ Authorization = 'Bearer <ORTHOS_BEARER_TOKEN>' }
```

Chat completion:

```powershell
Invoke-RestMethod `
  -Uri 'http://100.114.166.24:8787/v1/chat/completions' `
  -Method Post `
  -Headers @{
    Authorization = 'Bearer <ORTHOS_BEARER_TOKEN>'
    'Content-Type' = 'application/json'
  } `
  -Body '{
    "model": "Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6",
    "messages": [{"role": "user", "content": "Reply exactly: Orthos ready"}],
    "max_tokens": 12,
    "temperature": 0
  }'
```

## Troubleshooting

If the hostname endpoint is dead:

```text
Use http://100.114.166.24:8787/v1 instead.
```

If Kyle wants the hostname endpoint to work, enable Tailscale DNS on his machine:

```powershell
tailscale set --accept-dns=true
```

Check Serve status on Chris machine:

```powershell
tailscale serve status
```

Expected Serve status includes:

```text
|-- tcp://100.114.166.24:8787
|--> tcp://127.0.0.1:8787

https://chris13600k.tail406192.ts.net (tailnet only)
|-- / proxy http://127.0.0.1:8787
```

Check local listeners:

```powershell
Get-NetTCPConnection -LocalPort 8082,8787
```

Expected important listeners:

```text
127.0.0.1:8082    shared TabbyAPI
127.0.0.1:8787    Orthos auth proxy
100.114.166.24:8787 Tailscale Serve TCP fallback
```

If Orthos returns `401`, the API key is missing or wrong.

If Orthos returns `502`, the proxy cannot reach shared TabbyAPI on
`127.0.0.1:8082`.

If Orthos returns `503`, Kyle access may be disabled in:

```text
C:\LLM\state\proxy-state.json
```

## Security Notes

`100.114.166.24` is a Tailscale IP, not a public internet IP.
Only devices in the tailnet can route to it.

The IP fallback does not bypass the proxy. It still reaches:

```text
100.114.166.24:8787 -> auth proxy -> shared TabbyAPI
```

Raw shared TabbyAPI is not directly exposed:

```text
127.0.0.1:8082 only
```

The proxy does not log prompts or responses. It logs request metadata and status
to:

```text
C:\LLM\logs\tabby-auth-proxy.out.log
C:\LLM\logs\tabby-auth-proxy.err.log
C:\LLM\state\proxy-metrics.jsonl
```

## Test Results

Test date:

```text
2026-05-10T10:40:22.3389819-04:00
```

Tailscale Serve status:

```text
|-- tcp://chris13600k.tail406192.ts.net:8787 (TLS over TCP, tailnet only)
|-- tcp://100.114.166.24:8787
|-- tcp://[fd7a:115c:a1e0::9a38:a618]:8787
|--> tcp://127.0.0.1:8787

https://chris13600k.tail406192.ts.net (tailnet only)
|-- / proxy http://127.0.0.1:8787
```

DNS-free model listing:

```text
GET http://100.114.166.24:8787/v1/models
Result: 200 OK
Model: Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6
```

DNS-free chat completion:

```text
POST http://100.114.166.24:8787/v1/chat/completions
Prompt: Reply exactly: Orthos ready
Result: 200 OK
Response: Orthos ready
Completion id: cmpl-88c6ff30e3ef44ae8b0b14a84c00f44d
```

MagicDNS HTTPS model listing:

```text
GET https://chris13600k.tail406192.ts.net/v1/models
Result: 200 OK
Model: Qwen3-Coder-30B-A3B-Instruct-exl3-4.0bpw-H6
```

Conclusion:

```text
Orthos is reachable for Kyle through the authenticated proxy.
```

