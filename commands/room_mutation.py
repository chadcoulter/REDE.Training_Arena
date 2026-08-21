from evennia import create_object
from evennia.utils.search import search_object

from .challenge_runtime import ArenaCommand

EXIT = "typeclasses.exits.Exit"
ROOM = "typeclasses.rooms.Room"

HORIZONTAL_DIRECTIONS = (
    "north",
    "northeast",
    "east",
    "southeast",
    "south",
    "southwest",
    "west",
    "northwest",
)
VERTICAL_DIRECTIONS = ("up", "down")
DIRECTIONAL_EXITS = (
    *HORIZONTAL_DIRECTIONS,
    *VERTICAL_DIRECTIONS,
    *(f"up-{direction}" for direction in HORIZONTAL_DIRECTIONS),
    *(f"down-{direction}" for direction in HORIZONTAL_DIRECTIONS),
)
DIRECTION_ALIASES = {
    "n": "north",
    "ne": "northeast",
    "e": "east",
    "se": "southeast",
    "s": "south",
    "sw": "southwest",
    "w": "west",
    "nw": "northwest",
    "u": "up",
    "d": "down",
}


def normalize_direction(value):
    direction = value.strip().lower().replace("_", "-").replace(" ", "-")
    direction = DIRECTION_ALIASES.get(direction, direction)
    for prefix in ("up-", "down-"):
        if direction.startswith(prefix):
            suffix = direction[len(prefix) :]
            suffix = DIRECTION_ALIASES.get(suffix, suffix)
            direction = prefix + suffix
            break
    return direction if direction in DIRECTIONAL_EXITS else None


def _require_admin(caller):
    room = caller.location
    if not room or room.db.admin_holder_id != caller.id:
        caller.msg("Room admin is required for this mutation.")
        return None
    return room


def _find_arena_room(name):
    matches = search_object(name)
    exact = []
    for obj in matches:
        try:
            if obj.is_typeclass(ROOM, exact=False) and obj.key.casefold() == name.casefold():
                exact.append(obj)
        except Exception:
            continue
    return exact[0] if len(exact) == 1 else None


class CmdAdminDescribe(ArenaCommand):
    """Set the theatre description of a non-core room before publication."""

    key = "admin/describe"
    locks = "cmd:all()"
    help_category = "Arena Admin"

    def func(self):
        room = _require_admin(self.caller)
        if not room:
            return
        if room.db.published_sealed:
            self.caller.msg("This room has been published; its theatre description is immutable.")
            return
        if room.tags.has("exit_creation_only", category="rede"):
            self.caller.msg("Core arena rooms are protected anchors; only exit creation is allowed here.")
            return
        text = self.args.strip()
        if not text:
            self.caller.msg("Usage: admin/describe <description>")
            return
        room.db.desc = text
        self.caller.msg("Room theatre updated.")


class CmdAdminOpen(ArenaCommand):
    """Open one directional exit, creating the destination room when needed."""

    key = "admin/open"
    locks = "cmd:all()"
    help_category = "Arena Admin"

    def func(self):
        room = _require_admin(self.caller)
        if not room:
            return
        if "=" not in self.args:
            self.caller.msg("Usage: admin/open <direction>=<destination room>")
            return

        raw_direction, destination_name = (part.strip() for part in self.args.split("=", 1))
        direction = normalize_direction(raw_direction)
        if not direction:
            self.caller.msg(
                "Exit must occupy one spatial direction: north/northeast/east/southeast/"
                "south/southwest/west/northwest, up/down, or an up-/down- diagonal."
            )
            return
        if not destination_name:
            self.caller.msg("A destination room is required.")
            return

        occupied_directions = {
            normalize_direction(obj.key) for obj in room.exits if normalize_direction(obj.key)
        }
        if direction in occupied_directions:
            self.caller.msg(f"The {direction} exit slot is already occupied in this room.")
            return

        destination = _find_arena_room(destination_name)
        created_room = False
        if destination is None:
            destination = create_object(ROOM, key=destination_name)
            destination.tags.add("arena_room", category="rede")
            destination.db.desc = ""
            destination.db.published_sealed = False
            destination.db.current_challenge_id = None
            destination.db.reserved_admin_actor_id = self.caller.id
            created_room = True

        created = create_object(EXIT, key=direction, location=room, destination=destination)
        self.caller.msg(
            f"Opened one-way {created.key} exit from {room.key} to {destination.key}. "
            + (
                "The new room reserves its initial admin claim for you when you enter."
                if created_room
                else "Creating a return exit requires admin authority in the destination room."
            )
        )
