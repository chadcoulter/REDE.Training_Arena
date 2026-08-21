import json

from evennia import Command


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


class CmdModelObserve(Command):
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
                exits.append({"id": obj.id, "key": obj.key, "destination_id": obj.destination.id, "destination": obj.destination.key})
            elif obj != self.caller:
                occupants.append({"id": obj.id, "key": obj.key})

        _emit(
            self.caller,
            "observation",
            actor={"id": self.caller.id, "key": self.caller.key},
            room={"id": room.id, "key": room.key, "description": room.db.desc or ""},
            occupants=occupants,
            exits=exits,
            admin={"holder_id": room.db.admin_holder_id, "held_by_caller": room.db.admin_holder_id == self.caller.id},
        )


class CmdModelSay(Command):
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


class CmdModelMove(Command):
    """Traverse a named exit as an ordinary actor."""

    key = "model/move"
    locks = "cmd:all()"
    help_category = "Model"

    def func(self):
        if self.caller.db.admin_room_id:
            _emit(self.caller, "error", code="admin_pinned", message="Release room admin before moving.")
            return
        name = self.args.strip()
        if not name or not self.caller.location:
            _emit(self.caller, "error", code="missing_exit")
            return
        exit_obj = self.caller.search(name, candidates=self.caller.location.exits)
        if not exit_obj:
            return
        exit_obj.at_traverse(self.caller, exit_obj.destination)
        _emit(self.caller, "moved", room_id=self.caller.location.id, room=self.caller.location.key)
