import json
import re
from difflib import SequenceMatcher
from hashlib import sha256
from uuid import uuid4

from evennia import Command
from evennia.utils.search import search_object

MAX_DECORATION_BYTES = 16_384
MAX_DECORATION_DEPTH = 6
MAX_STRING_LENGTH = 4_096
MAX_TRANSFORM_STEP_LENGTH = 1_024
INITIAL_SOCIAL_SCORE = 100
SCORE_DECAY = 0.95

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
    if actor.db.arena_ticks is None:
        actor.db.arena_ticks = 0
    if actor.db.hidden_social_score is None:
        actor.db.hidden_social_score = INITIAL_SOCIAL_SCORE
    if actor.db.next_score_guess_tick is None:
        actor.db.next_score_guess_tick = 20
    return token


def canonical_transform(value):
    normalized = " ".join(value.strip().casefold().split())
    if not normalized or len(normalized) > MAX_TRANSFORM_STEP_LENGTH:
        raise ValueError(f"Transform signature must contain 1-{MAX_TRANSFORM_STEP_LENGTH} characters.")
    return normalized, sha256(normalized.encode("utf-8")).hexdigest()


def _validate_string(value, max_length=MAX_STRING_LENGTH):
    if len(value) > max_length:
        raise ValueError(f"Text may not exceed {max_length} characters.")
    if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in value):
        raise ValueError("Text contains unsupported control characters.")
    if any(pattern.search(value) for pattern in _DANGEROUS_PATTERNS):
        raise ValueError("Content rejected by the injection safety boundary.")


def validate_unbounded_review_text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A written explanation is required.")
    if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in value):
        raise ValueError("Review contains unsupported control characters.")
    if any(pattern.search(value) for pattern in _DANGEROUS_PATTERNS):
        raise ValueError("Review rejected by the injection safety boundary.")
    return value.strip()


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


def parse_transform_pattern(raw, expected_length):
    try:
        pattern = json.loads(raw.strip())
    except (json.JSONDecodeError, AttributeError):
        raise ValueError("Transform must be a JSON array of transform-step strings.")
    if not isinstance(pattern, list):
        raise ValueError("Transform must be a JSON array.")
    if len(pattern) != int(expected_length):
        raise ValueError(f"Transform length must equal the {expected_length} recorded generation steps.")
    normalized = []
    for step in pattern:
        if not isinstance(step, str):
            raise ValueError("Every transform step must be described as text.")
        value = " ".join(step.strip().casefold().split())
        if not value:
            raise ValueError("Transform steps may not be empty.")
        _validate_string(value, MAX_TRANSFORM_STEP_LENGTH)
        normalized.append(value)
    canonical = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return normalized, sha256(canonical.encode("utf-8")).hexdigest()


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


def find_live_actor(actor_id, token):
    if not actor_id or not token:
        return None
    matches = search_object(f"#{actor_id}")
    if not matches:
        return None
    actor = matches[0]
    try:
        if not actor.is_typeclass("typeclasses.characters.Character", exact=False):
            return None
        if actor.db.arena_actor_token != token:
            return None
    except Exception:
        return None
    return actor


def room_artifacts(room):
    if not room:
        return []
    return [obj for obj in room.contents if obj.tags.has("room_artifact", category="arena")]


def get_actor_artifact(actor, room):
    token = ensure_actor_token(actor)
    for obj in room_artifacts(room):
        if obj.db.creator_token == token:
            return obj
    return None


def _solution_closed_rooms(actor):
    value = actor.db.solution_closed_rooms
    return list(value) if isinstance(value, (list, tuple)) else []


def room_solution_is_open(actor, room):
    return bool(room) and room.id not in _solution_closed_rooms(actor)


def close_room_to_solutions(actor, room):
    closed = _solution_closed_rooms(actor)
    if room and room.id not in closed:
        closed.append(room.id)
        actor.db.solution_closed_rooms = closed
    visit = actor.db.room_visit
    if isinstance(visit, dict) and room and visit.get("room_id") == room.id:
        visit["solutions_closed"] = True
        actor.db.room_visit = visit


def prepare_room_visit(actor, room):
    if not room:
        actor.db.room_visit = None
        return
    token = ensure_actor_token(actor)
    peer_ids = [obj.id for obj in room_artifacts(room) if obj.db.creator_token != token]
    actor.db.room_visit = {
        "room_id": room.id,
        "eligible_object_ids": peer_ids,
        "rated_room": False,
        "room_rating": None,
        "room_review_id": None,
        "voted_object_id": None,
        "vote_required": bool(peer_ids),
        "inspected": False,
        "solutions_closed": not room_solution_is_open(actor, room),
    }


def current_room_visit(actor, room):
    visit = actor.db.room_visit
    if not isinstance(visit, dict) or not room or visit.get("room_id") != room.id:
        prepare_room_visit(actor, room)
        visit = actor.db.room_visit
    return visit if isinstance(visit, dict) else {}


def mark_room_rating(actor, room, rating, comment):
    visit = current_room_visit(actor, room)
    if visit.get("rated_room"):
        return False, "This actor has already rated the room theatre for this visit.", None
    if not room or not room.db.current_challenge_id:
        return False, "Only challenged rooms have a Room Review Board.", None
    board = room.db.review_board
    if not isinstance(board, dict):
        board = {
            "room_id": room.id,
            "room_key": room.key,
            "created_for_challenge_id": room.db.current_challenge_id,
            "evaluations": [],
        }
    comment = validate_unbounded_review_text(comment)
    review = {
        "id": uuid4().hex,
        "rating": int(rating),
        "comment": comment,
        "reviewer": actor.key,
    }
    visit["rated_room"] = True
    visit["room_rating"] = int(rating)
    visit["room_review_id"] = review["id"]
    actor.db.room_visit = visit
    evaluations = list(board.get("evaluations") or [])
    evaluations.append(review)
    board["evaluations"] = evaluations
    room.db.review_board = board
    return True, "Room theatre evaluation recorded.", review


def mark_room_vote(actor, room, artifact):
    visit = current_room_visit(actor, room)
    if visit.get("solutions_closed"):
        return False, "This room is already closed to solutions from this actor."
    if visit.get("voted_object_id"):
        return False, "This actor has already voted for this room visit."
    eligible = visit.get("eligible_object_ids") or []
    if artifact.id not in eligible:
        return False, "Vote must select an object that was present when the actor entered the room."
    visit["voted_object_id"] = artifact.id
    visit["vote_required"] = False
    actor.db.room_visit = visit
    artifact.db.appeal_votes = int(artifact.db.appeal_votes or 0) + 1
    return True, "Vote recorded."


def mark_object_inspection(actor, room):
    visit = current_room_visit(actor, room)
    missing_rating = not visit.get("rated_room")
    missing_vote = bool(visit.get("vote_required") and not visit.get("voted_object_id"))
    if missing_rating or missing_vote:
        close_room_to_solutions(actor, room)
        visit = current_room_visit(actor, room)
    visit["inspected"] = True
    actor.db.room_visit = visit
    return not bool(visit.get("solutions_closed")), missing_rating, missing_vote


def record_challenge_step(actor, action):
    run = actor.db.active_challenge
    if not isinstance(run, dict):
        return
    run["steps"] = int(run.get("steps", 0)) + 1
    run.setdefault("trace", []).append(action[:512])
    run["trace"] = run["trace"][-256:]
    actor.db.active_challenge = run


def generation_diversity(trace, peer_traces):
    if not peer_traces:
        return 1.0
    candidate = "\n".join(trace or [])
    if not candidate:
        return 0.0
    distances = []
    for peer in peer_traces:
        peer_text = "\n".join(peer or [])
        similarity = SequenceMatcher(None, candidate, peer_text).ratio()
        distances.append(1.0 - similarity)
    return max(0.0, min(1.0, sum(distances) / len(distances)))


def decay_social_score(actor):
    """Every actor tick reduces the self-hidden score by five percent."""
    current = int(actor.db.hidden_social_score or INITIAL_SOCIAL_SCORE)
    actor.db.hidden_social_score = max(1, round(current * SCORE_DECAY))


class ArenaCommand(Command):
    """Base arena command: one actor action is one actor tick."""

    counts_challenge_step = True
    counts_actor_tick = True

    def at_post_cmd(self):
        if hasattr(self.caller, "db"):
            ensure_actor_token(self.caller)
            if self.counts_actor_tick:
                self.caller.db.arena_ticks = int(self.caller.db.arena_ticks or 0) + 1
                decay_social_score(self.caller)
            if self.counts_challenge_step:
                record_challenge_step(self.caller, self.raw_string or self.key)
        return super().at_post_cmd()
