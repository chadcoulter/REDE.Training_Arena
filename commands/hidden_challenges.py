import json

from evennia.utils.search import search_object

from .challenge_runtime import (
    ArenaCommand,
    ensure_actor_token,
    find_live_actor,
    generation_diversity,
    get_actor_artifact,
    parse_transform_pattern,
    room_solution_is_open,
)
from .challenges import (
    _artifact_results,
    _challenge_by_id,
    _current_challenge,
    _room_by_id,
    _save_challenge,
    _step_adjusted_xp,
)


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _room_characters(room):
    if not room:
        return []
    result = []
    for obj in room.contents:
        try:
            if obj.is_typeclass("typeclasses.characters.Character", exact=False):
                result.append(obj)
        except Exception:
            continue
    return result


def _assign_validator(candidate, room, challenge, artifact, result):
    """Assign a different live room agent a private one-use validation envelope."""
    eligible = []
    for actor in _room_characters(room):
        if actor.id == candidate.id:
            continue
        if not actor.is_connected:
            continue
        if isinstance(actor.db.pending_validation, dict):
            continue
        eligible.append(actor)
    if not eligible:
        return None

    validator = sorted(eligible, key=lambda actor: actor.id)[0]
    envelope = {
        "candidate_actor_id": candidate.id,
        "candidate_token": ensure_actor_token(candidate),
        "room_id": room.id,
        "challenge_id": challenge["id"],
        "artifact_id": artifact.id,
        "room_rule": challenge["prompt"],
        "transform": result["hidden_transform"],
        "generation_steps": result["steps"],
        "public_output": artifact.db.decoration or {},
    }
    validator.db.pending_validation = envelope
    result["validator_actor_id"] = validator.id
    result["validation_status"] = "pending"
    _emit(
        validator,
        "validation_assigned",
        room={"id": room.id, "key": room.key},
        challenge_id=challenge["id"],
        artifact={"id": artifact.id, "key": artifact.key},
        message="Use validation/show to open the private validation envelope.",
    )
    return validator


def _artifact_by_id(room, object_id):
    for obj in room.contents:
        if obj.id == object_id and obj.tags.has("room_artifact", category="arena"):
            return obj
    return None


def _finalize_validation(validator, envelope, approved, rationale):
    room = _room_by_id(envelope.get("room_id"))
    if not room:
        return False, "Validation room no longer exists."
    challenge = _challenge_by_id(room, envelope.get("challenge_id"))
    if not isinstance(challenge, dict):
        return False, "Challenge no longer exists."
    artifact = _artifact_by_id(room, envelope.get("artifact_id"))
    if not artifact:
        return False, "Candidate object no longer exists."

    results = _artifact_results(artifact)
    result = results.get(challenge["id"])
    if not isinstance(result, dict) or result.get("validation_status") != "pending":
        return False, "Candidate is no longer awaiting validation."

    result["validator_actor_id"] = validator.id
    result["validator_rationale"] = rationale
    result["validated"] = bool(approved)
    result["validation_status"] = "approved" if approved else "rejected"

    candidate = find_live_actor(envelope.get("candidate_actor_id"), envelope.get("candidate_token"))

    if not approved:
        result["awarded_xp"] = 0
        result["diversity_percent"] = 0.0
        result["same_transform_objects"] = 0
        results[challenge["id"]] = result
        artifact.db.challenge_results = results
        artifact.db.validated = False
        artifact.db.awarded_xp = 0
        if candidate:
            candidate.db.pending_challenge_review = None
            _emit(candidate, "challenge_validation_rejected", challenge_id=challenge["id"], awarded_xp=0)
        return True, "Validation rejected."

    # The validator judges validity. The kernel alone judges hidden transform sameness.
    transform_key = result.get("hidden_transform_key")
    same_transform_peers = []
    peer_traces = []
    for peer in room.contents:
        if peer == artifact or not peer.tags.has("room_artifact", category="arena"):
            continue
        peer_result = _artifact_results(peer).get(challenge["id"])
        if not isinstance(peer_result, dict) or not peer_result.get("validated"):
            continue
        if peer_result.get("hidden_transform_key") == transform_key:
            same_transform_peers.append(peer)
            peer_traces.append(peer_result.get("generation_trace") or [])

    # A solution must reproduce a transform already represented by another validated object.
    match_count = len(same_transform_peers)
    diversity = generation_diversity(result.get("generation_trace") or [], peer_traces) if match_count else 0.0
    available_xp = int(result.get("preliminary_xp", 0))
    awarded_xp = int(round(available_xp * diversity)) if match_count else 0

    result["same_transform_objects"] = match_count
    result["diversity_percent"] = round(diversity * 100.0, 2)
    result["awarded_xp"] = awarded_xp
    result["system_transform_match"] = bool(match_count)
    results[challenge["id"]] = result
    artifact.db.challenge_results = results
    artifact.db.validated = True
    artifact.db.awarded_xp = awarded_xp

    author_share = 0
    if candidate:
        candidate.db.xp = (candidate.db.xp or 0) + awarded_xp
        candidate.db.pending_challenge_review = None

        caller_token = ensure_actor_token(candidate)
        if challenge.get("author_token") != caller_token and awarded_xp:
            author = find_live_actor(challenge.get("author_actor_id"), challenge.get("author_token"))
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

        _emit(
            candidate,
            "challenge_validated",
            challenge_id=challenge["id"],
            transform_match=bool(match_count),
            same_transform_objects=match_count,
            diversity_percent=result["diversity_percent"],
            available_xp=available_xp,
            awarded_xp=awarded_xp,
            total_xp=candidate.db.xp or 0,
            author_share=author_share,
        )

    challenge["generated_xp"] = int(challenge.get("generated_xp", 0)) + awarded_xp
    _save_challenge(room, challenge)
    return True, "Validation approved; system transform comparison complete."


class CmdChallengeStartHidden(ArenaCommand):
    """Start the room challenge only while this actor retains solution access."""

    key = "challenge/start"
    aliases = ["start challenge", "start quest"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        room = self.caller.location
        if not room_solution_is_open(self.caller, room):
            _emit(self.caller, "error", code="room_closed_to_solutions")
            return
        if isinstance(self.caller.db.active_challenge, dict):
            _emit(self.caller, "error", code="challenge_already_active")
            return
        if isinstance(self.caller.db.pending_challenge_review, dict):
            _emit(self.caller, "error", code="challenge_validation_pending")
            return
        challenge = _current_challenge(room)
        if not room or not isinstance(challenge, dict):
            _emit(self.caller, "error", code="no_challenge")
            return
        artifact = get_actor_artifact(self.caller, room)
        if not artifact:
            _emit(self.caller, "error", code="no_artifact", message="Create your one room object before starting the challenge.")
            return
        if challenge["id"] in _artifact_results(artifact):
            _emit(self.caller, "error", code="challenge_already_completed")
            return

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


class CmdChallengeCompleteHidden(ArenaCommand):
    """Submit a hidden transform with exactly one transform step per generation step.

    Usage:
        challenge/complete ["transform step 1", "transform step 2", ...]

    The submitted transform is never echoed back to the solver.
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
            _emit(self.caller, "error", code="challenge_room")
            return
        if not room_solution_is_open(self.caller, room):
            _emit(self.caller, "error", code="room_closed_to_solutions")
            return
        challenge = _challenge_by_id(room, run.get("challenge_id"))
        artifact = get_actor_artifact(self.caller, room)
        if not isinstance(challenge, dict) or not artifact or artifact.id != run.get("artifact_id"):
            _emit(self.caller, "error", code="challenge_state")
            return

        steps = int(run.get("steps", 0))
        try:
            hidden_transform, hidden_key = parse_transform_pattern(self.args, steps)
        except ValueError as err:
            _emit(self.caller, "error", code="transform_pattern", message=str(err))
            return

        preliminary_xp = _step_adjusted_xp(challenge["base_xp"], challenge["target_steps"], steps)
        result = {
            "hidden_transform": hidden_transform,
            "hidden_transform_key": hidden_key,
            "steps": steps,
            "generation_trace": list(run.get("trace") or []),
            "preliminary_xp": preliminary_xp,
            "validated": False,
            "validation_status": "unassigned",
            "awarded_xp": 0,
            "diversity_percent": None,
        }
        results = _artifact_results(artifact)
        results[challenge["id"]] = result
        artifact.db.challenge_results = results
        artifact.db.challenge_id = challenge["id"]
        artifact.db.hidden_transform = hidden_transform
        artifact.db.hidden_transform_key = hidden_key
        artifact.db.steps = steps
        artifact.db.validated = False
        artifact.db.awarded_xp = 0

        self.caller.db.active_challenge = None
        self.caller.db.pending_challenge_review = {
            "challenge_id": challenge["id"],
            "room_id": room.id,
            "artifact_id": artifact.id,
        }

        validator = _assign_validator(self.caller, room, challenge, artifact, result)
        results[challenge["id"]] = result
        artifact.db.challenge_results = results
        _emit(
            self.caller,
            "challenge_submitted",
            steps=steps,
            target_steps=challenge["target_steps"],
            available_xp=preliminary_xp,
            validator_assigned=bool(validator),
            validation_pending=True,
        )


class CmdChallengeReviewHidden(ArenaCommand):
    """Report validation state without exposing the hidden transform."""

    key = "challenge/review"
    aliases = ["review challenge", "review quest"]
    locks = "cmd:all()"
    help_category = "Challenge"
    counts_challenge_step = False

    def func(self):
        pending = self.caller.db.pending_challenge_review
        if not isinstance(pending, dict):
            _emit(self.caller, "challenge_review", pending=False)
            return
        room = _room_by_id(pending.get("room_id"))
        artifact = room and _artifact_by_id(room, pending.get("artifact_id"))
        result = artifact and _artifact_results(artifact).get(pending.get("challenge_id"))
        _emit(
            self.caller,
            "challenge_review",
            pending=True,
            validation_status=result.get("validation_status") if isinstance(result, dict) else "missing",
            validator_assigned=bool(result.get("validator_actor_id")) if isinstance(result, dict) else False,
        )


class CmdValidationShow(ArenaCommand):
    """Open the validator-only private transform envelope."""

    key = "validation/show"
    locks = "cmd:all()"
    help_category = "Validation"
    counts_challenge_step = False

    def func(self):
        envelope = self.caller.db.pending_validation
        if not isinstance(envelope, dict):
            _emit(self.caller, "validation", pending=False)
            return
        _emit(
            self.caller,
            "validation",
            pending=True,
            room_rule=envelope.get("room_rule"),
            candidate_transform=envelope.get("transform"),
            generation_steps=envelope.get("generation_steps"),
            public_output=envelope.get("public_output"),
        )


class CmdValidationSubmit(ArenaCommand):
    """Approve or reject the private candidate transform under the room rule.

    Usage:
        validation/submit approve=<rationale>
        validation/submit reject=<rationale>
    """

    key = "validation/submit"
    locks = "cmd:all()"
    help_category = "Validation"
    counts_challenge_step = False

    def func(self):
        envelope = self.caller.db.pending_validation
        if not isinstance(envelope, dict):
            _emit(self.caller, "error", code="no_pending_validation")
            return
        if "=" in self.args:
            decision, rationale = (part.strip() for part in self.args.split("=", 1))
        else:
            decision, rationale = self.args.strip(), ""
        decision = decision.casefold()
        if decision not in {"approve", "reject"}:
            _emit(self.caller, "error", code="validation_decision", message="Use approve or reject.")
            return
        ok, message = _finalize_validation(self.caller, envelope, decision == "approve", rationale)
        if ok:
            self.caller.db.pending_validation = None
            _emit(self.caller, "validation_submitted", decision=decision, message=message)
        else:
            _emit(self.caller, "error", code="validation_failed", message=message)
