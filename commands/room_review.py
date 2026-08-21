import json

from .challenge_runtime import (
    ArenaCommand,
    current_room_visit,
    mark_object_inspection,
    mark_room_vote,
    room_artifacts,
)


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _resolve_artifact(caller, query):
    room = caller.location
    if not room:
        return None, "You are not in a room."
    artifacts = room_artifacts(room)
    if not query:
        return None, "An object name or dbref is required."
    query = query.strip()
    if query.startswith("#") and query[1:].isdigit():
        object_id = int(query[1:])
        matches = [obj for obj in artifacts if obj.id == object_id]
    else:
        exact = [obj for obj in artifacts if obj.key.casefold() == query.casefold()]
        matches = exact or [obj for obj in artifacts if query.casefold() in obj.key.casefold()]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, "No room object matches that target."
    return None, "Object target is ambiguous; use a unique name or dbref."


def public_output(artifact):
    decoration = artifact.db.decoration or {}
    if isinstance(decoration, dict):
        if "display" in decoration:
            return decoration["display"]
        if "description" in decoration:
            return decoration["description"]
    return artifact.key


class CmdObjectVote(ArenaCommand):
    """Vote for the most appealing object before inspecting room objects.

    Usage:
        object/vote <object>
    """

    key = "object/vote"
    aliases = ["vote object"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        artifact, error = _resolve_artifact(self.caller, self.args)
        if error:
            _emit(self.caller, "error", code="object_vote", message=error)
            return
        ok, message = mark_room_vote(self.caller, self.caller.location, artifact)
        if not ok:
            _emit(self.caller, "error", code="object_vote", message=message)
            return
        _emit(
            self.caller,
            "object_voted",
            object={"id": artifact.id, "key": artifact.key},
            appeal_votes=int(artifact.db.appeal_votes or 0),
        )


class CmdObjectInspect(ArenaCommand):
    """Inspect a room object without exposing its hidden transform.

    If a vote was required for this room visit and the actor inspects before
    voting, the inspection still succeeds but this room becomes permanently
    closed to challenge solutions from that actor.

    Usage:
        object/inspect <object>
    """

    key = "object/inspect"
    aliases = ["inspect object"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        artifact, error = _resolve_artifact(self.caller, self.args)
        if error:
            _emit(self.caller, "error", code="object_inspect", message=error)
            return

        still_open = mark_object_inspection(self.caller, self.caller.location)
        results = artifact.db.challenge_results
        public_results = {}
        if isinstance(results, dict):
            for challenge_id, result in results.items():
                if not isinstance(result, dict):
                    continue
                public_results[challenge_id] = {
                    "steps": result.get("steps"),
                    "validated": bool(result.get("validated")),
                    "awarded_xp": result.get("awarded_xp", 0),
                    "diversity_percent": result.get("diversity_percent"),
                }

        visit = current_room_visit(self.caller, self.caller.location)
        _emit(
            self.caller,
            "object_inspected",
            object={
                "id": artifact.id,
                "key": artifact.key,
                "public_output": public_output(artifact),
                "decoration": artifact.db.decoration or {},
                "appeal_votes": int(artifact.db.appeal_votes or 0),
                "challenge_results": public_results,
            },
            solution_access_open=still_open,
            voted_object_id=visit.get("voted_object_id"),
        )
