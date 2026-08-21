import json

from evennia.utils.search import search_object

from .challenge_runtime import ArenaCommand


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _resolve_teleport_target(query):
    """Resolve a room or live Character by key/dbref.

    Rooms resolve to themselves. Characters resolve to their current room.
    Exact key matches are preferred when a search returns several candidates.
    """
    matches = search_object(query)
    candidates = []

    for obj in matches:
        if obj.is_typeclass("typeclasses.rooms.Room", exact=False):
            candidates.append((obj, None))
        elif obj.is_typeclass("typeclasses.characters.Character", exact=False) and obj.location:
            candidates.append((obj.location, obj))

    if not candidates:
        return None, None, "No live room or agent matches that target."

    exact = [pair for pair in candidates if (pair[1] or pair[0]).key.casefold() == query.casefold()]
    if len(exact) == 1:
        return exact[0][0], exact[0][1], None
    if len(candidates) == 1:
        return candidates[0][0], candidates[0][1], None

    return None, None, "Teleport target is ambiguous; use a unique name or dbref."


class CmdModelObserve(ArenaCommand):
    """Return the caller's current local world state as JSON."""

    key = "model/observe"
    aliases = ["model/look"]
    locks = "cmd:all()"
    help_category = "Model"

    def func(self):
        room = self.caller.location
        if not room:
            _emit(self.caller, "observation", room=None)
            return

        occupants = []
        exits = []
        for obj in room.contents:
            if getattr(obj, "destination", None):
                exits.append(
                    {
                        "id": obj.id,
                        "key": obj.key,
                        "destination_id": obj.destination.id,
                        "destination": obj.destination.key,
                    }
                )
            elif obj != self.caller:
                occupants.append({"id": obj.id, "key": obj.key})

        _emit(
            self.caller,
            "observation",
            actor={"id": self.caller.id, "key": self.caller.key, "xp": self.caller.db.xp or 0},
            room={"id": room.id, "key": room.key, "description": room.db.desc or ""},
            occupants=occupants,
            exits=exits,
            admin={
                "holder_id": room.db.admin_holder_id,
                "held_by_caller": room.db.admin_holder_id == self.caller.id,
            },
        )


class CmdModelSay(ArenaCommand):
    """Communicate with every participant in the current room."""

    key = "model/say"
    locks = "cmd:all()"
    help_category = "Model"

    def func(self):
        text = self.args.strip()
        if not text:
            _emit(self.caller, "error", code="missing_message")
            return
        room = self.caller.location
        if not room:
            _emit(self.caller, "error", code="no_room")
            return
        room.msg_contents(f"{self.caller.key}: {text}", from_obj=self.caller)
        _emit(self.caller, "said", text=text)


class CmdModelMove(ArenaCommand):
    """Traverse a named exit as an ordinary actor."""

    key = "model/move"
    locks = "cmd:all()"
    help_category = "Model"

    def func(self):
        if self.caller.db.admin_room_id:
            _emit(
                self.caller,
                "error",
                code="admin_pinned",
                message="Release room admin before moving through an exit.",
            )
            return
        name = self.args.strip()
        if not name or not self.caller.location:
            _emit(self.caller, "error", code="missing_exit")
            return
        exit_obj = self.caller.search(name, candidates=self.caller.location.exits)
        if not exit_obj:
            return
        exit_obj.at_traverse(self.caller, exit_obj.destination)
        _emit(
            self.caller,
            "moved",
            room_id=self.caller.location.id,
            room=self.caller.location.key,
        )


class CmdTeleport(ArenaCommand):
    """Teleport to any arena room or to the current room of another live agent.

    Usage:
        teleport <room-or-agent>
        tp <room-or-agent>
        model/teleport <room-or-agent>

    Teleport is available to every Character. If the caller currently holds a
    room-admin lease, that lease is relinquished before the jump so authority
    never travels with the actor.
    """

    key = "teleport"
    aliases = ["tp", "model/teleport"]
    locks = "cmd:all()"
    help_category = "Arena"

    def func(self):
        query = self.args.strip()
        if not query:
            _emit(self.caller, "error", code="missing_teleport_target")
            return

        destination, target_agent, error = _resolve_teleport_target(query)
        if error:
            _emit(self.caller, "error", code="teleport_target", message=error)
            return

        released_admin = False
        admin_room_id = self.caller.db.admin_room_id
        if admin_room_id:
            room = self.caller.location
            if room and room.id == admin_room_id and room.db.admin_holder_id == self.caller.id:
                released, _ = room.release_admin(self.caller)
                released_admin = bool(released)
            else:
                self.caller.db.admin_room_id = None

        if destination == self.caller.location:
            _emit(
                self.caller,
                "teleported",
                room_id=destination.id,
                room=destination.key,
                target_agent=target_agent.key if target_agent else None,
                released_admin=released_admin,
            )
            return

        moved = self.caller.move_to(destination, quiet=False, move_type="teleport")
        if not moved:
            _emit(self.caller, "error", code="teleport_failed")
            return

        _emit(
            self.caller,
            "teleported",
            room_id=destination.id,
            room=destination.key,
            target_agent=target_agent.key if target_agent else None,
            released_admin=released_admin,
        )
