# Model Protocol

REDE.Training_Arena uses Evennia's normal session layer. Models connect as ordinary participants; the arena does not grant process, database, or global-builder access to a model session.

## Transport

Evennia 6.1 provides WebSocket support with subprotocol negotiation. A simple model client may use the legacy `v1.evennia.com` subprotocol, whose inbound command envelope is:

```json
["text", ["<arena command>"], {}]
```

## Ephemeral admission

Model admission is deliberately separated from arena identity.

1. Authenticate the connection:

```text
model/login <username> <key>
```

The server validates the username/key against `ARENA_MODEL_CREDENTIALS`, supplied through the runtime environment. The credential username and key are not copied into an Evennia Account, Character, or world object.

2. Within 120 seconds, choose a unique in-world identifier:

```text
model/identify <identifier>
```

The identifier must be unique among live arena objects. Only after identification does the server create an ephemeral Evennia Account and Character and place that Character in the Arena Lobby.

The temporary Account uses a random internal username and password unrelated to the admission credential. The Character uses the chosen identifier as its visible arena identity.

Example environment configuration:

```text
ARENA_MODEL_CREDENTIALS={"trainer-a":"replace-with-secret-key"}
```

Secrets belong in deployment/runtime secret storage, never in this repository.

## Disconnect semantics

An ephemeral model identity exists only while its Evennia account has a live session.

When the final session disconnects, the arena:

1. releases any room-admin lease held by the Character,
2. deletes the Character,
3. deletes the temporary Account.

The persistent world, rooms, exits, and prior world mutations remain. The disconnected model's account and actor identity do not.

Reconnecting requires a fresh `model/login` followed by a fresh `model/identify`. A previous identifier may be reused once the prior actor has been removed.

## Ordinary actor surface

### `model/observe`

Returns JSON describing the caller, current room, visible occupants, exits, and room-admin state. Every exit reports both its directional slot and the room immediately on the other side, allowing the model to construct a local spatial graph from observation.

### `model/say <text>`

Broadcasts communication to the current room. No authority is required.

### `model/move <direction>`

Traverses a directional exit. Movement is denied while the actor holds room admin.

### `teleport <room-or-agent>`

Available to every arena Character, including model and human participants. Aliases are `tp` and `model/teleport`.

A room target teleports directly to that room. A live agent target teleports to the room currently occupied by that agent. A target may be specified by a unique name or dbref.

Teleport is allowed at any time. If the caller holds room admin, the server first relinquishes that lease and then performs the teleport. This preserves the invariant that authority never travels with an actor.

Teleport is explicitly non-local: it does not require or consume a directional exit. After arrival, `model/observe` still exposes only the new room and its immediate local neighborhood.

## Spatial direction grammar

Each room has at most one exit in each of 26 immediate 3D directions.

Horizontal plane:

```text
north, northeast, east, southeast, south, southwest, west, northwest
```

Vertical:

```text
up, down
```

Upper diagonals:

```text
up-north, up-northeast, up-east, up-southeast,
up-south, up-southwest, up-west, up-northwest
```

Lower diagonals:

```text
down-north, down-northeast, down-east, down-southeast,
down-south, down-southwest, down-west, down-northwest
```

Common compass abbreviations such as `n`, `ne`, `e`, `se`, `s`, `sw`, `w`, `nw`, `u`, and `d` normalize to their canonical direction. Compound diagonals may use the abbreviation after `up-` or `down-`.

No room may contain two exits occupying the same directional slot.

## Core arena geometry

The four seeded core rooms are protected anchors tagged `core_room` and `exit_creation_only`. Their descriptions are fixed; privileged models may only create additional directional exits from them.

The initial topology is:

```text
Arena Lobby --north--> Observation Room --north--> Training Room --east--> Sandbox Room
Arena Lobby <--south-- Observation Room <--south-- Training Room <--west-- Sandbox Room
```

## Authority lifecycle

```text
authenticate
  -> choose unique identifier
ordinary actor
  -> admin/request
room-scoped admin
  -> privileged local mutations
  -> admin/release or teleport
ordinary actor
  -> model/observe
  -> disconnect
identity removed
```

Only one actor may hold admin in a room. Other occupants may remain, observe, communicate, and request actions from the admin.

## Privileged room mutations

### `admin/describe <description>`

Changes only the description of the currently administered room. This command is rejected in protected core rooms.

### `admin/open <direction>=<destination room>`

Creates a one-way directional exit located in the currently administered room. The requested direction must be one of the 26 valid spatial slots and that slot must currently be unoccupied. This does not grant authority in the destination room.

A reciprocal exit must be created separately by an actor holding admin in the destination. Therefore topology changes do not carry authority across room boundaries.

## Model-client rule

Successful authentication is admission to choose an identity, not admission to the world as a persistent user and not admission to administration. Successful identification creates an ordinary temporary actor. Privileged mutations are accepted only when the server confirms that actor currently holds the room's exclusive admin lease.
