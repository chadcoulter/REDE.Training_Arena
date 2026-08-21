# REDE.Training_Arena

AI Model Training Arena built on Evennia 6.1.

## Purpose

The arena provides a persistent multiplayer world in which humans, models, scripted agents, and later resolver implementations can share rooms, communicate, act, and inspect the consequences of prior actions.

Evennia remains an upstream dependency rather than vendored source so the arena can track the maintained MUD runtime without carrying a large fork.

## Authority invariants

- Any number of ordinary occupants may share a room.
- At most one actor may hold admin authority in a room at a time.
- Admin authority is scoped to the room in which it was acquired.
- An actor holding room admin cannot leave that room.
- The actor must release admin before moving.
- Entering another room requires a new admin request.
- Non-admin occupants may communicate with the current room admin and request privileged actions.

## Current commands

- `admin/request` — request admin authority for the current room.
- `admin/release` — relinquish current room authority.
- `admin/status` — inspect whether the current room has an admin.

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

`typeclasses/rooms.py` owns the room-local single-admin lease. `typeclasses/characters.py` prevents movement while an actor holds a lease. `commands/room_admin.py` exposes the authority lifecycle to connected actors, and `commands/default_cmdsets.py` registers those commands with Evennia.

The next layer is a model-facing connection protocol that maps model sessions onto ordinary arena actors rather than granting database or process access.

## Upstream

Runtime: Evennia 6.1.0, BSD licensed: https://github.com/evennia/evennia
