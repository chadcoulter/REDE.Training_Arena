import json
from uuid import uuid4

from .challenge_runtime import ArenaCommand, ensure_actor_token, validate_decoration
from .challenges import MAX_BASE_XP, MAX_TARGET_STEPS, _save_new_challenge


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


class CmdChallengeDefinePublished(ArenaCommand):
    """Define the room challenge after its theatre has been established.

    Usage:
        challenge/define <target-steps> <base-xp>=<challenge text>

    The admin may revise the challenge while it remains physically in the room.
    Once the established admin leaves for the first time, the room is published
    and both theatre description and challenge definition become immutable.
    """

    key = "challenge/define"
    aliases = ["admin/challenge"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        room = self.caller.location
        if not room or room.db.admin_holder_id != self.caller.id:
            _emit(self.caller, "error", code="room_admin_required")
            return
        if room.db.published_sealed:
            _emit(
                self.caller,
                "error",
                code="room_published",
                message="This room has been published; its challenge is immutable.",
            )
            return
        if not room.has_theatre:
            _emit(
                self.caller,
                "error",
                code="theatre_required",
                message="Set the room theatre with admin/describe before defining a challenge.",
            )
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
            _emit(self.caller, "error", code="challenge_target")
            return
        if not 0 <= base_xp <= MAX_BASE_XP:
            _emit(self.caller, "error", code="challenge_xp")
            return
        if len(prompt) > 8_192:
            _emit(self.caller, "error", code="challenge_prompt")
            return
        try:
            validate_decoration(prompt)
        except ValueError as err:
            _emit(self.caller, "error", code="challenge_safety", message=str(err))
            return

        challenge = {
            "id": uuid4().hex,
            "prompt": prompt,
            "target_steps": target_steps,
            "base_xp": base_xp,
            "author_actor_id": self.caller.id,
            "author_token": ensure_actor_token(self.caller),
            "generated_xp": 0,
        }
        _save_new_challenge(room, challenge)
        _emit(
            self.caller,
            "challenge_defined",
            room=room.key,
            challenge={
                "id": challenge["id"],
                "prompt": challenge["prompt"],
                "target_steps": challenge["target_steps"],
                "base_xp": challenge["base_xp"],
            },
            room_established=room.is_established,
            publication="The theatre and challenge seal on the admin's first departure.",
        )
