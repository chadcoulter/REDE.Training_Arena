import json

from evennia import create_object

from .challenge_runtime import (
    ArenaCommand,
    ensure_actor_token,
    get_actor_artifact,
    merge_decoration,
    parse_decoration,
    validate_decoration,
)

ARTIFACT_TYPECLASS = "typeclasses.objects.RoomArtifact"
MAX_ARTIFACT_NAME = 80


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


class CmdObjectCreate(ArenaCommand):
    """Create the caller's single persistent object in the current room."""

    key = "object/create"
    aliases = ["artifact/create"]
    locks = "cmd:all()"
    help_category = "Challenge"

    def func(self):
        room = self.caller.location
        if not room:
            _emit(self.caller, "error", code="no_room")
            return
        if get_actor_artifact(self.caller, room):
            _emit(self.caller, "error", code="artifact_limit", message="This actor already has its one object in this room.")
            return
        name = " ".join(self.args.strip().split())
        if not name or len(name) > MAX_ARTIFACT_NAME:
            _emit(self.caller, "error", code="artifact_name", message=f"Object name must contain 1-{MAX_ARTIFACT_NAME} characters.")
            return
        try:
            validate_decoration(name)
        except ValueError as err:
            _emit(self.caller, "error", code="artifact_safety", message=str(err))
            return
        token = ensure_actor_token(self.caller)
        artifact = create_object(ARTIFACT_TYPECLASS, key=name, location=room, home=room)
        artifact.db.creator_token = token
        artifact.db.creator_actor_id = self.caller.id
        artifact.db.decoration = {}
        _emit(self.caller, "artifact_created", artifact={"id": artifact.id, "key": artifact.key}, room={"id": room.id, "key": room.key})


class CmdObjectDecorate(ArenaCommand):
    """Merge safe data-only decoration into the caller's room object."""

    key = "object/decorate"
    aliases = ["artifact/decorate"]
    locks = "cmd:all()"
    help_category = "Challenge"

    def func(self):
        room = self.caller.location
        if not room:
            _emit(self.caller, "error", code="no_room")
            return
        artifact = get_actor_artifact(self.caller, room)
        if not artifact:
            _emit(self.caller, "error", code="no_artifact", message="Create your one room object before decorating it.")
            return
        try:
            patch = parse_decoration(self.args)
            artifact.db.decoration = merge_decoration(artifact.db.decoration, patch)
        except ValueError as err:
            _emit(self.caller, "error", code="artifact_safety", message=str(err))
            return
        _emit(self.caller, "artifact_decorated", artifact={"id": artifact.id, "key": artifact.key}, decoration=artifact.db.decoration)


class CmdObjectShow(ArenaCommand):
    """Inspect the caller's own persistent object without exposing transforms."""

    key = "object/show"
    aliases = ["artifact/show"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        room = self.caller.location
        artifact = room and get_actor_artifact(self.caller, room)
        if not artifact:
            _emit(self.caller, "artifact", artifact=None)
            return
        results = artifact.db.challenge_results
        public_results = {}
        if isinstance(results, dict):
            for challenge_id, result in results.items():
                if isinstance(result, dict):
                    public_results[challenge_id] = {
                        "steps": result.get("steps"),
                        "validated": bool(result.get("validated")),
                        "awarded_xp": result.get("awarded_xp", 0),
                        "diversity_percent": result.get("diversity_percent"),
                    }
        _emit(self.caller, "artifact", artifact={
            "id": artifact.id,
            "key": artifact.key,
            "decoration": artifact.db.decoration or {},
            "appeal_votes": int(artifact.db.appeal_votes or 0),
            "challenge_results": public_results,
        })
