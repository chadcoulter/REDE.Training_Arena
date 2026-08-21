import { createServer } from "node:http";
import net from "node:net";
import { randomUUID } from "node:crypto";

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";

const PORT = Number(process.env.PORT ?? 8787);
const MCP_PATH = "/mcp";
const ARENA_HOST = process.env.ARENA_HOST ?? "127.0.0.1";
const ARENA_PORT = Number(process.env.ARENA_PORT ?? 4000);
const CONNECT_TIMEOUT_MS = Number(process.env.ARENA_CONNECT_TIMEOUT_MS ?? 5000);
const DEFAULT_SETTLE_MS = Number(process.env.ARENA_SETTLE_MS ?? 250);
const MAX_WAIT_MS = 5000;
const MAX_BUFFER_CHARS = 200000;
const MCP_BEARER_TOKEN = process.env.MCP_BEARER_TOKEN ?? "";

const sessions = new Map();

function clampWait(value) {
  const number = Number(value ?? DEFAULT_SETTLE_MS);
  if (!Number.isFinite(number)) return DEFAULT_SETTLE_MS;
  return Math.max(0, Math.min(MAX_WAIT_MS, Math.floor(number)));
}

function textResult(message, structuredContent = {}) {
  return {
    content: [{ type: "text", text: message }],
    structuredContent,
  };
}

function normalizeText(text) {
  return text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

function appendOutput(session, text) {
  if (!text) return;
  session.buffer += normalizeText(text);
  if (session.buffer.length > MAX_BUFFER_CHARS) {
    session.buffer = session.buffer.slice(-MAX_BUFFER_CHARS);
  }
  session.lastActivityAt = Date.now();
}

function telnetDecode(session, chunk) {
  const bytes = Buffer.concat([session.telnetRemainder, chunk]);
  const output = [];
  let i = 0;

  while (i < bytes.length) {
    const byte = bytes[i];
    if (byte !== 255) {
      output.push(byte);
      i += 1;
      continue;
    }

    if (i + 1 >= bytes.length) break;
    const command = bytes[i + 1];

    // Escaped IAC byte.
    if (command === 255) {
      output.push(255);
      i += 2;
      continue;
    }

    // WILL/WONT/DO/DONT + option. Refuse optional Telnet features; the arena
    // command protocol only needs a clean line-oriented byte stream.
    if ([251, 252, 253, 254].includes(command)) {
      if (i + 2 >= bytes.length) break;
      const option = bytes[i + 2];
      const responseCommand = command === 251 || command === 252 ? 254 : 252;
      if (!session.socket.destroyed) {
        session.socket.write(Buffer.from([255, responseCommand, option]));
      }
      i += 3;
      continue;
    }

    // Sub-negotiation: IAC SB ... IAC SE.
    if (command === 250) {
      let end = i + 2;
      let found = false;
      while (end + 1 < bytes.length) {
        if (bytes[end] === 255 && bytes[end + 1] === 240) {
          found = true;
          break;
        }
        end += 1;
      }
      if (!found) break;
      i = end + 2;
      continue;
    }

    // Other two-byte Telnet commands.
    i += 2;
  }

  session.telnetRemainder = bytes.subarray(i);
  return Buffer.from(output).toString("utf8");
}

function publicSession(session) {
  return {
    sessionId: session.id,
    label: session.label,
    connected: session.connected && !session.socket.destroyed,
    host: ARENA_HOST,
    port: ARENA_PORT,
    createdAt: session.createdAt,
    lastActivityAt: session.lastActivityAt,
    bufferedCharacters: session.buffer.length,
  };
}

function getSession(sessionId) {
  const session = sessions.get(sessionId);
  if (!session) throw new Error(`Unknown arena session: ${sessionId}`);
  return session;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForQuiet(session, startLength, settleMs) {
  const quietMs = clampWait(settleMs);
  if (quietMs === 0) return;

  const deadline = Date.now() + MAX_WAIT_MS;
  let observedLength = session.buffer.length;
  let quietSince = Date.now();

  while (Date.now() < deadline) {
    await wait(Math.min(50, quietMs || 50));
    const currentLength = session.buffer.length;
    if (currentLength !== observedLength) {
      observedLength = currentLength;
      quietSince = Date.now();
    }
    if (currentLength > startLength && Date.now() - quietSince >= quietMs) return;
    if (!session.connected) return;
  }
}

async function openArenaSession(label) {
  const id = randomUUID();
  const socket = new net.Socket();
  socket.setNoDelay(true);

  const session = {
    id,
    label: label || `arena-${id.slice(0, 8)}`,
    socket,
    connected: false,
    buffer: "",
    telnetRemainder: Buffer.alloc(0),
    createdAt: new Date().toISOString(),
    lastActivityAt: Date.now(),
  };

  sessions.set(id, session);

  socket.on("data", (chunk) => appendOutput(session, telnetDecode(session, chunk)));
  socket.on("error", (error) => appendOutput(session, `\n[adapter socket error: ${error.message}]\n`));
  socket.on("close", () => {
    session.connected = false;
    session.lastActivityAt = Date.now();
  });

  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      socket.destroy();
      reject(new Error(`Timed out connecting to ${ARENA_HOST}:${ARENA_PORT}`));
    }, CONNECT_TIMEOUT_MS);

    socket.once("connect", () => {
      clearTimeout(timer);
      session.connected = true;
      session.lastActivityAt = Date.now();
      resolve();
    });
    socket.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    socket.connect(ARENA_PORT, ARENA_HOST);
  }).catch((error) => {
    sessions.delete(id);
    throw error;
  });

  await waitForQuiet(session, 0, DEFAULT_SETTLE_MS);
  return session;
}

function drain(session) {
  const output = session.buffer;
  session.buffer = "";
  return output;
}

function createArenaMcpServer() {
  const server = new McpServer(
    { name: "rede-training-arena", version: "0.1.0" },
    {
      instructions:
        "This is a thin transport into a persistent REDE Training Arena. Connect first, then send arena commands. Use receive when more output may be pending. The adapter does not implement game rules; the Evennia arena is authoritative.",
    },
  );

  server.registerTool(
    "arena_connect",
    {
      title: "Connect to arena",
      description: "Use this when you need a new live session to the configured REDE Training Arena.",
      inputSchema: {
        label: z.string().min(1).max(80).optional(),
      },
      outputSchema: {
        sessionId: z.string(),
        connected: z.boolean(),
        output: z.string(),
      },
      annotations: {
        readOnlyHint: false,
        destructiveHint: false,
        openWorldHint: true,
        idempotentHint: false,
      },
    },
    async ({ label }) => {
      try {
        const session = await openArenaSession(label);
        const output = drain(session);
        return textResult(
          `Connected to the arena as adapter session ${session.id}.`,
          { sessionId: session.id, connected: true, output },
        );
      } catch (error) {
        return textResult(`Arena connection failed: ${error.message}`, {
          sessionId: "",
          connected: false,
          output: "",
        });
      }
    },
  );

  server.registerTool(
    "arena_send",
    {
      title: "Send arena command",
      description: "Use this when you have a live arena session and want to send exactly one line-oriented command to Evennia.",
      inputSchema: {
        sessionId: z.string().uuid(),
        command: z.string().min(1).max(16384),
        settleMs: z.number().int().min(0).max(MAX_WAIT_MS).optional(),
      },
      outputSchema: {
        sessionId: z.string(),
        connected: z.boolean(),
        output: z.string(),
      },
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        openWorldHint: true,
        idempotentHint: false,
      },
    },
    async ({ sessionId, command, settleMs }) => {
      try {
        const session = getSession(sessionId);
        if (!session.connected || session.socket.destroyed) {
          return textResult("Arena session is disconnected.", {
            sessionId,
            connected: false,
            output: drain(session),
          });
        }

        const startLength = session.buffer.length;
        session.socket.write(`${command}\r\n`);
        session.lastActivityAt = Date.now();
        await waitForQuiet(session, startLength, settleMs);
        const output = drain(session);
        return textResult("Arena command sent.", {
          sessionId,
          connected: session.connected,
          output,
        });
      } catch (error) {
        return textResult(`Arena send failed: ${error.message}`, {
          sessionId,
          connected: false,
          output: "",
        });
      }
    },
  );

  server.registerTool(
    "arena_receive",
    {
      title: "Receive arena output",
      description: "Use this when a live arena session may have produced additional asynchronous output since the last command.",
      inputSchema: {
        sessionId: z.string().uuid(),
        waitMs: z.number().int().min(0).max(MAX_WAIT_MS).optional(),
      },
      outputSchema: {
        sessionId: z.string(),
        connected: z.boolean(),
        output: z.string(),
      },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: true,
        idempotentHint: false,
      },
    },
    async ({ sessionId, waitMs }) => {
      try {
        const session = getSession(sessionId);
        const before = session.buffer.length;
        await waitForQuiet(session, before, waitMs ?? DEFAULT_SETTLE_MS);
        return textResult("Arena output received.", {
          sessionId,
          connected: session.connected && !session.socket.destroyed,
          output: drain(session),
        });
      } catch (error) {
        return textResult(`Arena receive failed: ${error.message}`, {
          sessionId,
          connected: false,
          output: "",
        });
      }
    },
  );

  server.registerTool(
    "arena_status",
    {
      title: "Inspect arena adapter sessions",
      description: "Use this when you need to inspect one adapter session or list the currently known sessions.",
      inputSchema: {
        sessionId: z.string().uuid().optional(),
      },
      outputSchema: {
        sessions: z.array(z.object({
          sessionId: z.string(),
          label: z.string(),
          connected: z.boolean(),
          host: z.string(),
          port: z.number(),
          createdAt: z.string(),
          lastActivityAt: z.number(),
          bufferedCharacters: z.number(),
        })),
      },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: false,
        idempotentHint: true,
      },
    },
    async ({ sessionId }) => {
      try {
        const result = sessionId
          ? [publicSession(getSession(sessionId))]
          : [...sessions.values()].map(publicSession);
        return textResult(`Found ${result.length} arena adapter session(s).`, { sessions: result });
      } catch (error) {
        return textResult(`Arena status failed: ${error.message}`, { sessions: [] });
      }
    },
  );

  server.registerTool(
    "arena_disconnect",
    {
      title: "Disconnect arena session",
      description: "Use this when you are finished with a live arena session and want to close its TCP connection and remove adapter session state.",
      inputSchema: {
        sessionId: z.string().uuid(),
      },
      outputSchema: {
        sessionId: z.string(),
        disconnected: z.boolean(),
        output: z.string(),
      },
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        openWorldHint: true,
        idempotentHint: true,
      },
    },
    async ({ sessionId }) => {
      const session = sessions.get(sessionId);
      if (!session) {
        return textResult("Arena session was already absent.", {
          sessionId,
          disconnected: true,
          output: "",
        });
      }
      const output = drain(session);
      session.connected = false;
      session.socket.end();
      session.socket.destroy();
      sessions.delete(sessionId);
      return textResult("Arena session disconnected.", {
        sessionId,
        disconnected: true,
        output,
      });
    },
  );

  return server;
}

function authorized(req) {
  if (!MCP_BEARER_TOKEN) return true;
  return req.headers.authorization === `Bearer ${MCP_BEARER_TOKEN}`;
}

const httpServer = createServer(async (req, res) => {
  if (!req.url) {
    res.writeHead(400).end("Missing URL");
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host ?? "localhost"}`);

  if (req.method === "GET" && url.pathname === "/") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      service: "REDE Training Arena MCP Adapter",
      mcp: MCP_PATH,
      arenaConfigured: Boolean(ARENA_HOST && ARENA_PORT),
    }));
    return;
  }

  if (req.method === "OPTIONS" && url.pathname === MCP_PATH) {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "content-type, mcp-session-id, authorization",
      "Access-Control-Expose-Headers": "Mcp-Session-Id",
    });
    res.end();
    return;
  }

  const mcpMethods = new Set(["POST", "GET", "DELETE"]);
  if (url.pathname === MCP_PATH && req.method && mcpMethods.has(req.method)) {
    if (!authorized(req)) {
      res.writeHead(401, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "Unauthorized" }));
      return;
    }

    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Expose-Headers", "Mcp-Session-Id");

    const server = createArenaMcpServer();
    const transport = new StreamableHTTPServerTransport({
      sessionIdGenerator: undefined,
      enableJsonResponse: true,
    });

    res.on("close", () => {
      transport.close();
      server.close();
    });

    try {
      await server.connect(transport);
      await transport.handleRequest(req, res);
    } catch (error) {
      console.error("MCP request failed", error);
      if (!res.headersSent) res.writeHead(500).end("Internal server error");
    }
    return;
  }

  res.writeHead(404).end("Not Found");
});

function closeAllSessions() {
  for (const session of sessions.values()) {
    session.connected = false;
    session.socket.destroy();
  }
  sessions.clear();
}

process.on("SIGINT", () => {
  closeAllSessions();
  process.exit(0);
});
process.on("SIGTERM", () => {
  closeAllSessions();
  process.exit(0);
});

httpServer.listen(PORT, () => {
  console.log(`REDE Training Arena MCP adapter listening on http://localhost:${PORT}${MCP_PATH}`);
  console.log(`Arena target configured as ${ARENA_HOST}:${ARENA_PORT}`);
});
