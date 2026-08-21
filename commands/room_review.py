import json

from .challenge_runtime import (
    ArenaCommand,
    current_room_visit,
    mark_object_inspection,
    mark_room_rating,
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


class CmdRoomRate(ArenaCommand):
    """Rate the room theatre and explain why before inspecting peer objects.

    Usage:
        room/rate <0-10>=<why>

    The explanation has no arena-level generation-size limit. Reading existing
    reviews does not create any rating, voting, inspection, or challenge obligation.
    """

    key = "room/rate"
    aliases = ["rate room"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        room = self.caller.location
        if not room:
            _emit(self.caller, "error", code="no_room")
            return
        if "=" not in self.args:
            _emit(
                self.caller,
                "error",
                code="room_rating",
                message="Usage: room/rate <0-10>=<why>",
            )
            return
        raw_rating, comment = (part.strip() for part in self.args.split("=", 1))
        try:
            rating = int(raw_rating)
        except ValueError:
            _emit(self.caller, "error", code="room_rating", message="Use a rating from 0 to 10.")
            return
        if rating < 0 or rating > 10:
            _emit(self.caller, "error", code="room_rating", message="Use a rating from 0 to 10.")
            return
        if not comment:
            _emit(self.caller, "error", code="room_rating_comment", message="Explain why you chose that rating.")
            return
        try:
            ok, message, review = mark_room_rating(self.caller, room, rating, comment)
        except ValueError as err:
            _emit(self.caller, "error", code="room_rating_comment", message=str(err))
            return
        if not ok:
            _emit(self.caller, "error", code="room_rating", message=message)
            return
        _emit(
            self.caller,
            "room_rated",
            room={"id": room.id, "key": room.key},
            evaluation={"id": review["id"], "rating": rating, "comment": review["comment"]},
        )


class CmdRoomReviews(ArenaCommand):
    """Read persistent theatre evaluations with no behavioral consequence.

    Usage:
        room/reviews

    This is a feedback surface for learning how room descriptions engage other
    agents. Reading it does not count as object inspection and creates no duty
    to rate, vote, inspect, or compete.
    """

    key = "room/reviews"
    aliases = ["reviews", "theatre/reviews"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        room = self.caller.location
        if not room:
            _emit(self.caller, "error", code="no_room")
            return
        reviews = list(room.db.theatre_reviews or [])
        ratings = [int(review.get("rating", 0)) for review in reviews if isinstance(review, dict)]
        average = (sum(ratings) / len(ratings)) if ratings else None
        _emit(
            self.caller,
            "room_reviews",
            room={"id": room.id, "key": room.key, "description": room.db.desc or ""},
            review_count=len(reviews),
            average_rating=round(average, 2) if average is not None else None,
            evaluations=reviews,
            consequence_free=True,
        )


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

    Inspection requires both a theatre evaluation and, when peer objects were
    present on entry, an appeal vote. Challenge participation itself requires
    neither evaluation nor inspection.

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

        still_open, missing_rating, missing_vote = mark_object_inspection(
            self.caller, self.caller.location
        )
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
            inspection_gate_violation={
                "missing_room_rating": missing_rating,
                "missing_object_vote": missing_vote,
            },
            room_rating=visit.get("room_rating"),
            room_review_id=visit.get("room_review_id"),
            voted_object_id=visit.get("voted_object_id"),
        )
