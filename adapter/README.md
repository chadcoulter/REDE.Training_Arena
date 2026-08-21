# REDE Training Arena MCP Adapter

This directory contains a thin tool-only MCP adapter between ChatGPT/Codex and the REDE Training Arena's line-oriented Evennia transport.

The adapter deliberately owns no arena rules. It keeps network session state, forwards commands, buffers asynchronous output, and exposes that transport through MCP tools. Evennia remains authoritative for identity, rooms, challenges, ticks, score, tribbles, and all other world behavior.

## Tools

- `arena_connect` - open a new connection to the configured arena.
- `arena_send` - send one line-oriented arena command and return output received after it.
- `arena_receive` - drain additional asynchronous output from a live session.
- `arena_status` - inspect one or all adapter sessions.
- `arena_disconnect` - close and forget a session.

The arena target is configured by environment variables rather than by tool arguments. This prevents the adapter from becoming an arbitrary TCP proxy.

## Run locally

Requires Node.js 20+.

```bash
cd adapter
npm install
cp .env.example .env
# export values from .env using your preferred environment loader/shell
npm run check
npm start
```

The default MCP endpoint is:

```text
http://localhost:8787/mcp
```

The default arena target is:

```text
127.0.0.1:4000
```

Override it with `ARENA_HOST` and `ARENA_PORT` when Evennia is hosted elsewhere.

## Environment

- `PORT` - HTTP port for the MCP server. Default `8787`.
- `ARENA_HOST` - fixed Evennia host. Default `127.0.0.1`.
- `ARENA_PORT` - fixed Evennia Telnet port. Default `4000`.
- `ARENA_CONNECT_TIMEOUT_MS` - TCP connection timeout. Default `5000`.
- `ARENA_SETTLE_MS` - default quiet period used when collecting command output. Default `250`.
- `MCP_BEARER_TOKEN` - optional bearer token required on `/mcp` when non-empty.

Do not commit admission credentials or the bearer token. Arena credentials continue to travel through normal arena commands such as `model/login`; the adapter does not persist them separately.

## ChatGPT development loop

1. Start Evennia and make its model transport reachable from the adapter host.
2. Start this adapter.
3. Expose the adapter's HTTP port through a public HTTPS endpoint or development tunnel.
4. In ChatGPT Developer Mode, create/connect an app using the public URL ending in `/mcp`.
5. Call `arena_connect`, then use `arena_send` for `help`, `model/login`, `model/identify`, `model/observe`, and subsequent arena commands.
6. Use `arena_receive` when asynchronous room events may have arrived without a command response.
7. Call `arena_disconnect` when the actor session should end.

## Security boundary

The MCP client cannot choose an arbitrary destination host or port. The adapter process has one configured arena target. For an internet-facing deployment, use TLS at the reverse proxy/edge, set `MCP_BEARER_TOKEN` or a stronger authentication layer, keep the Evennia transport private when possible, and restrict outbound network access from the adapter host to the arena target.

## Current scope

This is the minimal transport adapter. It intentionally does not parse arena JSON into higher-level game-specific tools. That preserves the protocol boundary and allows humans, ChatGPT, other model providers, scripts, and future resolver clients to interact through the same authoritative arena command surface.
