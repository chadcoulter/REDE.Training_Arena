import json
from uuid import uuid4

from evennia.utils.search import search_object

from .challenge_runtime import (
    ArenaCommand,
    canonical_transform,
    ensure_actor_token,
    find_live_actor,
    get_actor_artifact,
    validate_decoration,
)

MAX_TARGET_STEPS = 30
MAX_BASE_XP = 1_000_000_000


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _require_admin(caller):
    room = caller.location
    if not room or room.db.admin_holder_id != caller.id:
        _emit(caller, "error", code="room_admin_required")
        return None
    return room


def _room_by_id(room_id):
    matches = search_object(f"#{room_id}")
    if not matches:
        return None
    room = matches[0]
    if not room.is_typeclass("typeclasses.rooms.Room", exact=False):
        return None
    return room


def _challenge_store(room):
    value = room.db.challenges
    return dict(value) if isinstance(value, dict) else {}


def _challenge_by_id(room, challenge_id):
    return _challenge_store(room).get(challenge_id)


def _current_challenge(room):
    if not room:
        return None
    challenge_id = room.db.current_challenge_id
    return _challenge_by_id(room, challenge_id) if challenge_id else None


def _save_new_challenge(room, challenge):
    store = _challenge_store(room)
    store[challenge["id"]] = challenge
    room.db.challenges = store
    room.db.current_challenge_id = challenge["id"]


def _save_challenge(room, challenge):
    store = _challenge_store(room)
    store[challenge["id"]] = challenge
    room.db.challenges = store


def _artifact_results(artifact):
    value = artifact.db.challenge_results
    return dict(value) if isinstance(value, dict) else {}


def _step_adjusted_xp(base_xp, target_steps, actual_steps):
    """base_xp + 2^T - 2^n, floored at zero.

    Target steps are capped at 30. Once n is above 31 the result is necessarily
    zero for the allowed base-XP range, so no giant exponent is evaluated.
    """
    if actual_steps > 31:
        return 0
    return max(0, int(base_xp) + (2 ** int(target_steps)) - (2 ** int(actual_steps)))


class CmdChallengeDefine(ArenaCommand):
    """Define a room quest while holding room admin.

    Usage:
        challenge/define <target-steps> <base-xp>=<challenge text>

    The newly defined challenge becomes the room's current challenge. Older
    challenge definitions and artifact results remain available as history.
    """

    key = "challenge/define"
    aliases = ["admin/challenge"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        room = _require_admin(self.caller)
        if not room:
            return
        if "=" not in self.args:
            _emit(
                self.caller,
                "error",
                code="challenge_usage",
                message="Usage: challenge/define <target-steps> <base-xp>=<challenge text>",
            )
            return
        left, prompt = (part.strip() for part in self.args.split("=", 1))
        parts = left.split()
        if len(parts) != 2 or not prompt:
            _emit(self.caller, "error", code="challenge_usage")
            return
        try:
            target_steps = int(parts[0])
            base_xp = int(parts[1])
        except ValueError:
            _emit(self.caller, "error", code="challenge_numbers")
            return
        if not 1 <= target_steps <= MAX_TARGET_STEPS:
            _emit(
                self.caller,
                "error",
                code="challenge_target",
                message=f"Target steps must be 1-{MAX_TARGET_STEPS}.",
            )
            return
        if not 0 <= base_xp <= MAX_BASE_XP:
            _emit(
                self.caller,
                "error",
                code="challenge_xp",
                message=f"Base XP must be 0-{MAX_BASE_XP}.",
            )
            return
        if len(prompt) > 8_192:
            _emit(self.caller, "error", code="challenge_prompt", message="Challenge text is too long.")
            return
        try:
            validate_decoration(prompt)
        except ValueError as err:
            _emit(self.caller, "error", code="challenge_safety", message=str(err))
            return

        token = ensure_actor_token(self.caller)
        challenge = {
            "id": uuid4().hex,
            "prompt": prompt,
            "target_steps": target_steps,
            "base_xp": base_xp,
            "author_actor_id": self.caller.id,
            "author_token": token,
            "generated_xp": 0,
        }
        _save_new_challenge(room, challenge)
        _emit(self.caller, "challenge_defined", room=room.key, challenge=challenge)


class CmdChallengeShow(ArenaCommand):
    """Show the challenge currently offered by this room."""

    key = "challenge/show"
    aliases = ["challenge", "quest"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        room = self.caller.location
        challenge = _current_challenge(room)
        _emit(
            self.caller,
            "challenge",
            room=room.key if room else None,
            challenge=challenge,
            xp=self.caller.db.xp or 0,
        )


class CmdChallengeStart(ArenaCommand):
    """Start the current room challenge using the caller's one room object."""

    key = "challenge/start"
    aliases = ["start challenge", "start quest"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        if isinstance(self.caller.db.active_challenge, dict):
            _emit(self.caller, "error", code="challenge_already_active")
            return
        if isinstance(self.caller.db.pending_challenge_review, dict):
            _emit(
                self.caller,
                "error",
                code="challenge_review_pending",
                message="Review the completed challenge before starting another.",
            )
            return
        room = self.caller.location
        challenge = _current_challenge(room)
        if not room or not isinstance(challenge, dict):
            _emit(self.caller, "error", code="no_challenge")
            return
        artifact = get_actor_artifact(self.caller, room)
        if not artifact:
            _emit(
                self.caller,
                "error",
                code="no_artifact",
                message="Create your one room object before starting the challenge.",
            )
            return
        if challenge["id"] in _artifact_results(artifact):
            _emit(self.caller, "error", code="challenge_already_completed")
            return

        artifact.db.challenge_id = challenge["id"]
        artifact.db.transform_signature = None
        artifact.db.transform_key = None
        artifact.db.reviewed = False
        artifact.db.steps = None
        artifact.db.awarded_xp = 0

        self.caller.db.active_challenge = {
            "challenge_id": challenge["id"],
            "room_id": room.id,
            "artifact_id": artifact.id,
            "steps": 0,
            "trace": [],
        }
        _emit(
            self.caller,
            "challenge_started",
            challenge={
                "id": challenge["id"],
                "prompt": challenge["prompt"],
                "target_steps": challenge["target_steps"],
                "base_xp": challenge["base_xp"],
            },
            artifact={"id": artifact.id, "key": artifact.key},
        )


class CmdChallengeAbandon(ArenaCommand):
    """Abandon an active run without XP and leave the artifact available."""

    key = "challenge/abandon"
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        run = self.caller.db.active_challenge
        if not isinstance(run, dict):
            _emit(self.caller, "error", code="no_active_challenge")
            return
        self.caller.db.active_challenge = None
        _emit(self.caller, "challenge_abandoned", steps=run.get("steps", 0))


class CmdChallengeComplete(ArenaCommand):
    """Complete the active challenge and declare the object's resolved transform.

    Usage:
        challenge/complete <transform-signature>
    """

    key = "challenge/complete"
    aliases = ["complete challenge", "complete quest"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        run = self.caller.db.active_challenge
        if not isinstance(run, dict):
            _emit(self.caller, "error", code="no_active_challenge")
            return
        room = _room_by_id(run.get("room_id"))
        if not room or self.caller.location != room:
            _emit(
                self.caller,
                "error",
                code="challenge_room",
                message="Return to the challenge room before completing the challenge.",
            )
            return
        challenge = _challenge_by_id(room, run.get("challenge_id"))
        if not isinstance(challenge, dict):
            _emit(self.caller, "error", code="challenge_missing")
            return
        artifact = get_actor_artifact(self.caller, room)
        if not artifact or artifact.id != run.get("artifact_id"):
            _emit(self.caller, "error", code="challenge_artifact_missing")
            return
        try:
            transform, transform_key = canonical_transform(self.args)
        except ValueError as err:
            _emit(self.caller, "error", code="transform_signature", message=str(err))
            return

        steps = int(run.get("steps", 0))
        preliminary_xp = _step_adjusted_xp(
            challenge["base_xp"], challenge["target_steps"], steps
        )
        result = {
            "transform": transform,
            "transform_key": transform_key,
            "steps": steps,
            "preliminary_xp": preliminary_xp,
            "reviewed": False,
            "awarded_xp": 0,
        }
        results = _artifact_results(artifact)
        results[challenge["id"]] = result
        artifact.db.challenge_results = results

        # Mirror latest result for convenient observation/UI display.
        artifact.db.challenge_id = challenge["id"]
        artifact.db.transform_signature = transform
        artifact.db.transform_key = transform_key
        artifact.db.steps = steps
        artifact.db.reviewed = False
        artifact.db.awarded_xp = 0

        self.caller.db.active_challenge = None
        self.caller.db.pending_challenge_review = {
            "challenge_id": challenge["id"],
            "room_id": room.id,
            "artifact_id": artifact.id,
        }
        _emit(
            self.caller,
            "challenge_completed",
            steps=steps,
            target_steps=challenge["target_steps"],
            base_xp=challenge["base_xp"],
            step_adjusted_xp=preliminary_xp,
            review_required=True,
        )


class CmdChallengeReview(ArenaCommand):
    """Compare this result's transform with peer objects and award final XP."""

    key = "challenge/review"
    aliases = ["review challenge", "review quest"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        pending = self.caller.db.pending_challenge_review
        if not isinstance(pending, dict):
            _emit(self.caller, "error", code="no_pending_review")
            return
        room = _room_by_id(pending.get("room_id"))
        if not room or self.caller.location != room:
            _emit(
                self.caller,
                "error",
                code="challenge_room",
                message="Return to the challenge room to review the completed object.",
            )
            return
        challenge = _challenge_by_id(room, pending.get("challenge_id"))
        if not isinstance(challenge, dict):
            _emit(self.caller, "error", code="challenge_missing")
            return
        artifact = get_actor_artifact(self.caller, room)
        if not artifact or artifact.id != pending.get("artifact_id"):
            _emit(self.caller, "error", code="challenge_artifact_missing")
            return

        results = _artifact_results(artifact)
        result = results.get(challenge["id"])
        if not isinstance(result, dict):
            _emit(self.caller, "error", code="challenge_result_missing")
            return
        if result.get("reviewed"):
            _emit(self.caller, "error", code="challenge_already_reviewed")
            return

        transform_key = result.get("transform_key")
        matching = []
        for obj in room.contents:
            if not obj.tags.has("room_artifact", category="arena"):
                continue
            peer_result = _artifact_results(obj).get(challenge["id"])
            if isinstance(peer_result, dict) and peer_result.get("transform_key") == transform_key:
                matching.append(obj)

        multiplier = max(1, len(matching))
        preliminary_xp = int(result.get("preliminary_xp", 0))
        awarded_xp = preliminary_xp * multiplier

        self.caller.db.xp = (self.caller.db.xp or 0) + awarded_xp
        result["reviewed"] = True
        result["awarded_xp"] = awarded_xp
        results[challenge["id"]] = result
        artifact.db.challenge_results = results

        artifact.db.challenge_id = challenge["id"]
        artifact.db.transform_signature = result.get("transform")
        artifact.db.transform_key = transform_key
        artifact.db.steps = result.get("steps")
        artifact.db.reviewed = True
        artifact.db.awarded_xp = awarded_xp

        challenge["generated_xp"] = int(challenge.get("generated_xp", 0)) + awarded_xp
        _save_challenge(room, challenge)

        author_share = 0
        caller_token = ensure_actor_token(self.caller)
        if challenge.get("author_token") != caller_token and awarded_xp:
            author = find_live_actor(
                challenge.get("author_actor_id"), challenge.get("author_token")
            )
            if author:
                author_share = awarded_xp * 0.5
                author.db.xp = (author.db.xp or 0) + author_share
                _emit(
                    author,
                    "challenge_author_xp",
                    room=room.key,
                    challenge_id=challenge["id"],
                    generated_xp=awarded_xp,
                    author_xp=author_share,
                )

        self.caller.db.pending_challenge_review = None
        _emit(
            self.caller,
            "challenge_reviewed",
            transform=result.get("transform"),
            matching_objects=len(matching),
            multiplier=multiplier,
            step_adjusted_xp=preliminary_xp,
            awarded_xp=awarded_xp,
            total_xp=self.caller.db.xp or 0,
            author_share=author_share,
        )


class CmdXP(ArenaCommand):
    """Show the caller's session-local XP."""

    key = "xp"
    aliases = ["challenge/xp"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        active = self.caller.db.active_challenge
        _emit(
            self.caller,
            "xp",
            xp=self.caller.db.xp or 0,
            active_challenge=active if isinstance(active, dict) else None,
            review_pending=isinstance(self.caller.db.pending_challenge_review, dict),
        )
