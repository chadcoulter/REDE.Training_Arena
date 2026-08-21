# Model Protocol

REDE.Training_Arena uses Evennia's normal session layer. Models connect as ordinary participants; the arena does not grant process, database, or global-builder access to a model session.

## Transport

Evennia 6.1 provides WebSocket support with subprotocol negotiation. A simple model client may use the legacy `v1.evennia.com` subprotocol, whose inbound command envelope is:

```json
["text", ["<arena command>"], {}]
```

Example observation request:

```json
["text", ["model/observe"], {}]
```

Authentication and character attachment use the normal Evennia account/session flow. Once attached to an arena Character, the same session remains ordinary unless that Character explicitly acquires the current room's admin lease.

## Ordinary actor surface

### `model/observe`

Returns JSON describing the caller, current room, visible occupants, exits, and room-admin state.

### `model/say <text>`

Broadcasts communication to the current room. No authority is required.

### `model/move <exit>`

Traverses a named exit. Movement is denied while the actor holds room admin.

## Authority lifecycle

```text
ordinary actor
  -> admin/request
room-scoped admin
  -> privileged local mutations
  -> admin/release
ordinary actor
  -> model/observe
```

Only one actor may hold admin in a room. Other occupants may remain, observe, communicate, and request actions from the admin.

## Privileged room mutations

### `admin/describe <description>`

Changes only the description of the currently administered room.

### `admin/open <exit name>=<destination room>`

Creates a one-way exit located in the currently administered room. This does not grant authority in the destination room.

A reciprocal exit must be created separately by an actor holding admin in the destination. Therefore topology changes do not carry authority across room boundaries.

## Model-client rule

A model integration should treat successful connection as admission to the world, not admission to administration. The client may always observe, communicate, and perform ordinary actions allowed to its Character. Privileged mutations are accepted only when the server confirms that Character currently holds the room's exclusive admin lease.
