import json
import re
from hashlib import sha256
from uuid import uuid4

from evennia import Command
from evennia.utils.search import search_object

MAX_DECORATION_BYTES = 16_384
MAX_DECORATION_DEPTH = 6
MAX_STRING_LENGTH = 4_096
MAX_TRANSFORM_LENGTH = 1_024

# Decorations are data-only. These markers are rejected as a second boundary
# against accidentally feeding executable/template payloads into future UIs.
_DANGEROUS_PATTERNS = (
    re.compile(r"<\s*script\b", re.I),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"data\s*:\s*text/html", re.I),
    re.compile(r"\{\{.*?\}\}", re.S),
    re.compile(r"\{%.*?%\}", re.S),
    re.compile(r"\b(__import__|eval|exec)\s*\(", re.I),
)


def ensure_actor_token(actor):
    token = actor.db.arena_actor_token
    if not token:
        token = uuid4().hex
        actor.db.arena_actor_token = token
    if actor.db.xp is None:
        actor.db.xp = 0
    return token


def canonical_transform(value):
    normalized = " ".join(value.strip().casefold().split())
    if not normalized or len(normalized) > MAX_TRANSFORM_LENGTH:
        raise ValueError(f"Transform signature must contain 1-{MAX_TRANSFORM_LENGTH} characters.")
    return normalized, sha256(normalized.encode("utf-8")).hexdigest()


def _validate_string(value):
    if len(value) > MAX_STRING_LENGTH:
        raise ValueError(f"Decoration strings may not exceed {MAX_STRING_LENGTH} characters.")
    if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in value):
        raise ValueError("Decoration contains unsupported control characters.")
    if any(pattern.search(value) for pattern in _DANGEROUS_PATTERNS):
        raise ValueError("Decoration rejected by the injection safety boundary.")


def validate_decoration(value, depth=0):
    if depth > MAX_DECORATION_DEPTH:
        raise ValueError("Decoration nesting is too deep.")
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        _validate_string(value)
        return
    if isinstance(value, list):
        for item in value:
            validate_decoration(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Decoration object keys must be strings.")
            _validate_string(key)
            validate_decoration(item, depth + 1)
        return
    raise ValueError("Decoration must contain only JSON-compatible data.")


def parse_decoration(raw):
    raw = raw.strip()
    if not raw:
        raise ValueError("Decoration is required.")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = {"description": raw}
    validate_decoration(value)
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_DECORATION_BYTES:
        raise ValueError(f"Decoration may not exceed {MAX_DECORATION_BYTES} encoded bytes.")
    return value


def merge_decoration(existing, patch):
    if not isinstance(existing, dict):
        existing = {}
    if isinstance(patch, dict):
        merged = dict(existing)
        merged.update(patch)
    else:
        merged = {"value": patch}
    validate_decoration(merged)
    encoded = json.dumps(merged, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_DECORATION_BYTES:
        raise ValueError(f"Decoration may not exceed {MAX_DECORATION_BYTES} encoded bytes.")
    return merged


def find_live_actor_by_token(token):
    if not token:
        return None
    matches = search_object("*")
    for obj in matches:
        try:
            if obj.is_typeclass("typeclasses.characters.Character", exact=False) and obj.db.arena_actor_token == token:
                return obj
        except Exception:
            continue
    return None


def get_actor_artifact(actor, room):
    token = ensure_actor_token(actor)
    for obj in room.contents:
        if obj.tags.has("room_artifact", category="arena") and obj.db.creator_token == token:
            return obj
    return None


def record_challenge_step(actor, action):
    run = actor.db.active_challenge
    if not isinstance(run, dict):
        return
    run["steps"] = int(run.get("steps", 0)) + 1
    run.setdefault("trace", []).append(action[:160])
    # Keep the trace bounded; step count remains authoritative.
    run["trace"] = run["trace"][-128:]
    actor.db.active_challenge = run


class ArenaCommand(Command):
    """Base arena command that counts one active-challenge generation step."""

    counts_challenge_step = True

    def at_post_cmd(self):
        if self.counts_challenge_step and hasattr(self.caller, "db"):
            record_challenge_step(self.caller, self.raw_string or self.key)
        return super().at_post_cmd()
