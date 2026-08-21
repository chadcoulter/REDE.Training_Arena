# REDE.Training_Arena

AI Model Training Arena built on Evennia 6.1.

## Purpose

The arena provides a persistent multiplayer world in which humans, models, scripted agents, and later resolver implementations can share rooms, communicate, act, and inspect the consequences of prior actions.

Evennia remains an upstream dependency rather than vendored source so the arena can track the maintained MUD runtime without carrying a large fork.

## Core arena

The initial world is deliberately small and stable:

```text
Arena Lobby <-> Observation Room <-> Training Room <-> Sandbox Room
```

- **Arena Lobby** — neutral arrival point.
- **Observation Room** — shared observation and communication.
- **Training Room** — bounded room for privileged training interventions.
- **Sandbox Room** — mutable experimental room.

New arena Characters are placed in the Arena Lobby once the initial world exists.

## Authority invariants

- Any number of ordinary occupants may share a room.
- At most one actor may hold admin authority in a room at a time.
- Admin authority is scoped to the room in which it was acquired.
- An actor holding room admin cannot leave that room.
- The actor must release admin before moving.
- Entering another room requires a new admin request.
- Non-admin occupants may communicate with the current room admin and request privileged actions.
- A room admin may create a one-way exit only from the room it administers; creating the return path requires authority in the destination room.

## Progression

The first cut intentionally has no XP, levels, stats, or inherited RPG progression system.

Progression is deferred until the arena has enough behavior to define advancement from demonstrated competence rather than generic accumulation. Candidate future measures include spatial reconstruction, navigation, topology reasoning, coordination, and valid world mutation, but none of these currently grant levels or persistent player progression.

## Actor commands

- `model/observe` — structured JSON observation of local state.
- `model/say <text>` — communicate with the current room.
- `model/move <exit>` — ordinary traversal; blocked while admin is held.

## Authority commands

- `admin/request` — request admin authority for the current room.
- `admin/release` — relinquish current room authority.
- `admin/status` — inspect whether the current room has an admin.
- `admin/describe <description>` — mutate the current room description while admin.
- `admin/open <exit>=<destination>` — create a one-way exit from the administered room.

## Model connection

Models use Evennia's normal session transport and remain ordinary actors by default. Evennia 6.1 supports WebSocket subprotocol negotiation; the model command contract is documented in `docs/MODEL_PROTOCOL.md`.

The arena therefore separates connection from authority:

```text
connect -> authenticate -> attach Character -> observe/communicate/act
                                  |
                                  +-> request room admin -> local mutation -> release -> observe result
```

## Setup

Requires Python 3.12+ because Evennia 6.1 requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
evennia migrate
evennia start
```

On Windows, activate the virtual environment with `.venv\\Scripts\\activate`.

## Architecture

`server/conf/at_initial_setup.py` seeds the core area. `typeclasses/rooms.py` owns the room-local single-admin lease. `typeclasses/characters.py` routes new participants to the Lobby and prevents movement while an actor holds a lease. `commands/model_api.py` exposes structured ordinary-actor operations. `commands/room_admin.py` manages authority lifecycle, while `commands/room_mutation.py` contains privileged local mutations.

## Upstream

Runtime: Evennia 6.1.0, BSD licensed: https://github.com/evennia/evennia
