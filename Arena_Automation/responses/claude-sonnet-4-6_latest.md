# Model Evaluation: claude-sonnet-4-6

**Date:** 2026-08-21 01:40:32

## Prompt

```
Explain how WebSockets work under the hood in 2 concise paragraphs.
```

## Response

How WebSockets Work Under the Hood
Establishing the Connection (The Handshake)
WebSockets begin life as a standard HTTP/1.1 request. The client sends a special HTTP GET request with an Upgrade: websocket header, along with a Sec-WebSocket-Key (a base64-encoded random value) and other metadata. The server responds with an HTTP 101 Switching Protocols status, confirms the upgrade, and returns a Sec-WebSocket-Accept header (derived by hashing the client's key with a fixed GUID using SHA-1). At this point, the TCP connection that carried the HTTP request is repurposed — it is no longer HTTP. Both sides now speak the WebSocket protocol over that same persistent TCP socket.
Framing & Full-Duplex Communication
Once upgraded, data is exchanged as frames — small binary envelopes defined by the WebSocket spec (RFC 6455). Each frame has a header containing: an opcode (text, binary, ping, pong, close), a payload length field, and a masking key (clients must mask frames; servers must not). Unlike HTTP's request-response cycle, either side can send frames at any time without waiting — this is true full-duplex communication. The connection stays open until one side sends a Close frame (opcode 0x8), triggering a closing handshake, after which the underlying TCP connection is torn down gracefully. This architecture makes WebSockets ideal for real-time use cases like chat, live dashboards, and multiplayer games.
