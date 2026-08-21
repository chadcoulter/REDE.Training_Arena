import json

from .challenge_runtime import ArenaCommand, ensure_actor_token

CANVAS_WIDTH = 64
CANVAS_HEIGHT = 16
GRAFFITI_SOLUTION_MULTIPLIER = 1.10
ORIENTATIONS = {
    "horizontal": (1, 0),
    "vertical": (0, 1),
    "diag-down": (1, 1),
    "diag-up": (1, -1),
}
ORIENTATION_ALIASES = {
    "h": "horizontal",
    "v": "vertical",
    "dd": "diag-down",
    "du": "diag-up",
    "diagonal-down": "diag-down",
    "diagonal-up": "diag-up",
}


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _cells_for(text, orientation, x, y):
    dx, dy = ORIENTATIONS[orientation]
    return [(x + (i * dx), y + (i * dy), ch) for i, ch in enumerate(text)]


def graffiti_contributed(actor, room):
    """Return True when this ephemeral actor has contributed to this room wall."""
    if not actor or not room:
        return False
    token = ensure_actor_token(actor)
    contributors = list(room.db.graffiti_contributors or [])
    return token in contributors


def graffiti_solution_multiplier(actor, room):
    """One bounded engagement bonus per actor per room; repeat painting does not stack."""
    return GRAFFITI_SOLUTION_MULTIPLIER if graffiti_contributed(actor, room) else 1.0


class CmdGraffitiPaint(ArenaCommand):
    """Paint the actor's arena name onto the current room's graffiti wall.

    Usage:
        graffiti/paint <horizontal|vertical|diag-down|diag-up> <x> <y>

    Every arena room has a graffiti wall. A new mark may overwrite differently
    oriented marks but may not overlap a mark with the same orientation.
    Painting is atomic: any invalid overlap or out-of-bounds cell rejects the
    whole mark.

    The actor's first valid contribution in a room qualifies that actor for the
    room's graffiti solution multiplier. Additional marks do not stack it.
    """

    key = "graffiti/paint"
    aliases = ["paint", "graffiti"]
    locks = "cmd:all()"
    help_category = "Arena"
    counts_challenge_step = False

    def func(self):
        room = self.caller.location
        if not room or not room.is_typeclass("typeclasses.rooms.Room", exact=False):
            _emit(self.caller, "error", code="graffiti_room", message="You must be in an arena room to paint graffiti.")
            return

        parts = self.args.split()
        if len(parts) != 3:
            _emit(self.caller, "error", code="graffiti_usage", message="Usage: graffiti/paint <orientation> <x> <y>")
            return

        orientation = ORIENTATION_ALIASES.get(parts[0].casefold(), parts[0].casefold())
        if orientation not in ORIENTATIONS:
            _emit(self.caller, "error", code="graffiti_orientation", message="Use horizontal, vertical, diag-down, or diag-up.")
            return
        try:
            x = int(parts[1])
            y = int(parts[2])
        except ValueError:
            _emit(self.caller, "error", code="graffiti_coordinates", message="x and y must be integers.")
            return

        text = self.caller.key
        cells = _cells_for(text, orientation, x, y)
        if any(cx < 0 or cy < 0 or cx >= CANVAS_WIDTH or cy >= CANVAS_HEIGHT for cx, cy, _ in cells):
            _emit(self.caller, "error", code="graffiti_bounds", message=f"The mark must fit inside the {CANVAS_WIDTH}x{CANVAS_HEIGHT} graffiti wall.")
            return

        existing = dict(room.db.graffiti_cells or {})
        conflicts = []
        for cx, cy, _ in cells:
            prior = existing.get(f"{cx},{cy}")
            if isinstance(prior, dict) and prior.get("orientation") == orientation:
                conflicts.append({"x": cx, "y": cy, "actor": prior.get("actor")})
        if conflicts:
            _emit(
                self.caller,
                "error",
                code="graffiti_parallel_overlap",
                message="A graffiti mark cannot overwrite another mark with the same orientation.",
                conflicts=conflicts,
            )
            return

        for cx, cy, ch in cells:
            existing[f"{cx},{cy}"] = {
                "char": ch,
                "orientation": orientation,
                "actor": self.caller.key,
            }
        room.db.graffiti_cells = existing

        token = ensure_actor_token(self.caller)
        contributors = list(room.db.graffiti_contributors or [])
        first_contribution = token not in contributors
        if first_contribution:
            contributors.append(token)
            room.db.graffiti_contributors = contributors

        _emit(
            self.caller,
            "graffiti_painted",
            room={"id": room.id, "key": room.key},
            text=text,
            orientation=orientation,
            x=x,
            y=y,
            first_room_contribution=first_contribution,
            solution_multiplier=graffiti_solution_multiplier(self.caller, room),
        )
