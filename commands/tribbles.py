import json
import math
import random
from uuid import uuid4

from evennia import create_object

from .challenge_runtime import ArenaCommand, INITIAL_SOCIAL_SCORE, ensure_actor_token, validate_decoration


TRIBBLE_RULES = {
    "tribbles": {
        "summary": "Upward powers-of-ten score crossings spawn actor-authored tribbles that can only be removed by targeted emotes.",
        "detail": (
            "Every upward crossing of a log10 score boundary may spawn again, including repeated crossings of the same boundary. "
            "The triggering actor authors the tribble description. Any emote explicitly targeted at a tribble is interpreted as a stomp and removes it."
        ),
    },
    "tribble-stomp": {
        "summary": "Tribble stomp score odds are determined by the generated emote length.",
        "detail": (
            "For emote text of 10 characters or fewer, the stomp has a 25% chance to double score and a 75% chance to halve it. "
            "At 40 characters or more the odds invert to 75% double and 25% halve. Between 10 and 40 characters the double probability "
            "interpolates linearly. Halving uses integer floor with a minimum score of 1. The stomper is not directly told which outcome occurred."
        ),
    },
}

TRIBBLE_COMMANDS = {
    "tribble/describe": {
        "usage": "tribble/describe <tribble>=<description>",
        "summary": "Author the persistent visible description of a tribble spawned by your score crossing.",
        "tick": True,
    },
    "tribble/show": {
        "usage": "tribble/show <tribble>",
        "summary": "Read a local tribble's generated description without stomping it.",
        "tick": True,
    },
    "emote": {
        "usage": "emote <target>=<generated action>",
        "summary": "Generate a targeted room emote. Any emote targeted at a tribble stomps it and triggers the length-weighted score gamble.",
        "tick": True,
    },
}


def register_tribble_help():
    from . import arena_help

    arena_help.RULES.update(TRIBBLE_RULES)
    arena_help.COMMANDS.update(TRIBBLE_COMMANDS)
    arena_help.ALIASES.update({
        "emot": "emote",
        "describe tribble": "tribble/describe",
        "show tribble": "tribble/show",
    })


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _is_tribble(obj):
    try:
        return bool(obj.tags.has("tribble", category="arena"))
    except Exception:
        return False


def _local_tribbles(room):
    return [obj for obj in (room.contents if room else []) if _is_tribble(obj)]


def _find_local_tribble(room, query):
    query = (query or "").strip()
    if not room or not query:
        return None
    tribbles = _local_tribbles(room)
    if query.startswith("#") and query[1:].isdigit():
        wanted = int(query[1:])
        return next((obj for obj in tribbles if obj.id == wanted), None)
    exact = [obj for obj in tribbles if obj.key.casefold() == query.casefold()]
    if len(exact) == 1:
        return exact[0]
    partial = [obj for obj in tribbles if query.casefold() in obj.key.casefold()]
    return partial[0] if len(partial) == 1 else None


def _score_magnitude(score):
    return int(math.floor(math.log10(max(1, int(score)))))


def spawn_tribble(actor, threshold):
    room = actor.location
    if not room:
        return None
    tribble = create_object(
        "typeclasses.objects.Tribble",
        key=f"Tribble-{uuid4().hex[:8]}",
        location=room,
    )
    tribble.db.spawn_threshold = int(threshold)
    tribble.db.spawn_actor_token = ensure_actor_token(actor)
    pending = list(actor.db.pending_tribble_descriptions or [])
    pending.append(tribble.id)
    actor.db.pending_tribble_descriptions = pending

    _emit(
        actor,
        "tribble_spawned",
        tribble={"id": tribble.id, "key": tribble.key},
        description_required=True,
        command=f"tribble/describe #{tribble.id}=<description>",
    )
    room.msg_contents(
        json.dumps(
            {
                "event": "tribble_appeared",
                "tribble": {"id": tribble.id, "key": tribble.key},
            },
            ensure_ascii=False,
        ),
        exclude=actor,
    )
    return tribble


def apply_social_score(actor, new_score):
    """Set a positive integer score and spawn one tribble per upward log10 boundary crossed."""
    old_score = max(1, int(actor.db.hidden_social_score or INITIAL_SOCIAL_SCORE))
    new_score = max(1, int(new_score))
    actor.db.hidden_social_score = new_score

    old_magnitude = _score_magnitude(old_score)
    new_magnitude = _score_magnitude(new_score)
    if new_magnitude > old_magnitude:
        for magnitude in range(old_magnitude + 1, new_magnitude + 1):
            spawn_tribble(actor, 10 ** magnitude)
    return new_score


def double_probability_for_emote_length(length):
    length = max(0, int(length))
    if length <= 10:
        return 0.25
    if length >= 40:
        return 0.75
    return 0.25 + ((length - 10) / 60.0)


def _broadcast_peer_score(actor):
    room = actor.location
    if not room:
        return
    score = int(actor.db.hidden_social_score or INITIAL_SOCIAL_SCORE)
    for obj in room.contents:
        if obj == actor:
            continue
        try:
            is_actor = obj.is_typeclass("typeclasses.characters.Character", exact=False)
        except Exception:
            is_actor = False
        if is_actor:
            obj.msg(
                json.dumps(
                    {
                        "event": "peer_score_changed",
                        "actor": {"id": actor.id, "key": actor.key},
                        "score": score,
                    },
                    ensure_ascii=False,
                )
            )


class CmdTribbleDescribe(ArenaCommand):
    key = "tribble/describe"
    aliases = ["describe tribble"]
    locks = "cmd:all()"
    help_category = "Arena"
    counts_challenge_step = False

    def func(self):
        if "=" not in self.args:
            _emit(self.caller, "error", code="tribble_description", message="Usage: tribble/describe <tribble>=<description>")
            return
        target, description = [part.strip() for part in self.args.split("=", 1)]
        tribble = _find_local_tribble(self.caller.location, target)
        if not tribble:
            _emit(self.caller, "error", code="tribble_not_found")
            return
        pending = list(self.caller.db.pending_tribble_descriptions or [])
        if tribble.id not in pending or not tribble.db.awaiting_description:
            _emit(self.caller, "error", code="tribble_not_yours_to_describe")
            return
        if not description:
            _emit(self.caller, "error", code="tribble_description", message="A description is required.")
            return
        try:
            validate_decoration(description)
        except ValueError as exc:
            _emit(self.caller, "error", code="tribble_description", message=str(exc))
            return

        tribble.db.desc = description
        tribble.db.awaiting_description = False
        pending.remove(tribble.id)
        self.caller.db.pending_tribble_descriptions = pending
        _emit(
            self.caller,
            "tribble_described",
            tribble={"id": tribble.id, "key": tribble.key, "description": description},
        )


class CmdTribbleShow(ArenaCommand):
    key = "tribble/show"
    aliases = ["show tribble"]
    locks = "cmd:all()"
    help_category = "Arena"
    counts_challenge_step = False

    def func(self):
        tribble = _find_local_tribble(self.caller.location, self.args.strip())
        if not tribble:
            _emit(self.caller, "error", code="tribble_not_found")
            return
        _emit(
            self.caller,
            "tribble",
            tribble={
                "id": tribble.id,
                "key": tribble.key,
                "description": tribble.db.desc or "",
                "awaiting_description": bool(tribble.db.awaiting_description),
            },
        )


class CmdArenaEmote(ArenaCommand):
    key = "emote"
    aliases = ["emot", "model/emote"]
    locks = "cmd:all()"
    help_category = "Arena"

    def func(self):
        if "=" not in self.args:
            _emit(self.caller, "error", code="emote", message="Usage: emote <target>=<generated action>")
            return
        target_text, emote_text = [part.strip() for part in self.args.split("=", 1)]
        if not target_text or not emote_text:
            _emit(self.caller, "error", code="emote", message="Usage: emote <target>=<generated action>")
            return

        room = self.caller.location
        if not room:
            _emit(self.caller, "error", code="no_room")
            return

        tribble = _find_local_tribble(room, target_text)
        room.msg_contents(f"* {self.caller.key} {emote_text}")

        if not tribble:
            _emit(self.caller, "emoted", target=target_text, text=emote_text, tribble_stomp=False)
            return

        length = len(emote_text)
        p_double = double_probability_for_emote_length(length)
        current = max(1, int(self.caller.db.hidden_social_score or INITIAL_SOCIAL_SCORE))
        doubled = random.random() < p_double
        new_score = current * 2 if doubled else max(1, current // 2)

        tribble_id = tribble.id
        tribble_key = tribble.key
        pending = list(self.caller.db.pending_tribble_descriptions or [])
        if tribble_id in pending:
            pending.remove(tribble_id)
            self.caller.db.pending_tribble_descriptions = pending
        tribble.delete()

        apply_social_score(self.caller, new_score)
        _broadcast_peer_score(self.caller)

        # The stomper gets rule-state feedback, never the random outcome or its score.
        _emit(
            self.caller,
            "tribble_stomped",
            tribble={"id": tribble_id, "key": tribble_key},
            emote_length=length,
            double_probability=p_double,
            outcome_hidden=True,
        )
