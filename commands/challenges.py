import json
from uuid import uuid4

from evennia.utils.search import search_object

from .challenge_runtime import (
    ArenaCommand,
    canonical_transform,
    ensure_actor_token,
    find_live_actor,
    get_actor_artifact,
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


def _artifact_completed_ids(artifact):
    value = artifact.db.completed_challenge_ids
    return list(value) if isinstance(value, (list, tuple)) else []


def _step_adjusted_xp(base_xp, target_steps, actual_steps):
    """base_xp + 2^T - 2^n, floored at zero.

    Target steps are capped at 30. Once n is above 31 the result is necessarily
    zero for the allowed base-XP range, so no giant exponent is evaluated.
    """
    if actual_steps > 31:
        return 0
    return max(0, int(base_xp) + (2 ** int(target_steps)) - (2 ** int(actual_steps)))


class CmdChallengeDefine(ArenaCommand):
    """Define the current room's quest challenge while holding room admin.

    Usage:
        challenge/define <target-steps> <base-xp>=<challenge text>

    Defining a new challenge replaces the room's currently offered challenge,
    but previous artifacts remain as persistent world state.
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
        room.db.challenge = challenge
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
        challenge = room and room.db.challenge
        _emit(
            self.caller,
            "challenge",
            room=room.key if room else None,
            challenge=challenge if isinstance(challenge, dict) else None,
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
        challenge = room and room.db.challenge
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
        if challenge["id"] in _artifact_completed_ids(artifact):
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
        challenge = room.db.challenge
        if not isinstance(challenge, dict) or challenge.get("id") != run.get("challenge_id"):
            _emit(self.caller, "error", code="challenge_replaced")
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
        artifact.db.transform_signature = transform
        artifact.db.transform_key = transform_key
        artifact.db.steps = steps
        artifact.db.reviewed = False

        self.caller.db.active_challenge = None
        self.caller.db.pending_challenge_review = {
            "challenge_id": challenge["id"],
            "room_id": room.id,
            "artifact_id": artifact.id,
            "steps": steps,
            "preliminary_xp": preliminary_xp,
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
        challenge = room.db.challenge
        if not isinstance(challenge, dict) or challenge.get("id") != pending.get("challenge_id"):
            _emit(self.caller, "error", code="challenge_replaced")
            return
        artifact = get_actor_artifact(self.caller, room)
        if not artifact or artifact.id != pending.get("artifact_id"):
            _emit(self.caller, "error", code="challenge_artifact_missing")
            return
        if artifact.db.reviewed:
            _emit(self.caller, "error", code="challenge_already_reviewed")
            return

        transform_key = artifact.db.transform_key
        matching = [
            obj
            for obj in room.contents
            if obj.tags.has("room_artifact", category="arena")
            and obj.db.challenge_id == challenge["id"]
            and obj.db.transform_key == transform_key
        ]
        multiplier = max(1, len(matching))
        preliminary_xp = int(pending.get("preliminary_xp", 0))
        awarded_xp = preliminary_xp * multiplier

        self.caller.db.xp = (self.caller.db.xp or 0) + awarded_xp
        artifact.db.reviewed = True
        artifact.db.awarded_xp = awarded_xp
        completed_ids = _artifact_completed_ids(artifact)
        if challenge["id"] not in completed_ids:
            completed_ids.append(challenge["id"])
            artifact.db.completed_challenge_ids = completed_ids

        challenge["generated_xp"] = int(challenge.get("generated_xp", 0)) + awarded_xp
        room.db.challenge = challenge

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
            transform=artifact.db.transform_signature,
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
