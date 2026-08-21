import json

from .challenge_runtime import ArenaCommand, INITIAL_SOCIAL_SCORE

GUESS_INTERVAL_TICKS = 20


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


class CmdScoreGuess(ArenaCommand):
    """Guess the actor's self-hidden social score once every 20 actor ticks.

    Usage:
        score/guess <integer>

    Other occupants see the guess and can observe the actor's score. The
    guessing actor never receives correctness, score, or score-delta feedback.
    An exact guess doubles the hidden score. The guess action itself is still
    an actor tick, so normal five-percent tick decay applies afterward.
    """

    key = "score/guess"
    aliases = ["guess score"]
    locks = "cmd:all()"
    help_category = "Arena"
    counts_challenge_step = False

    def func(self):
        try:
            guess = int(self.args.strip())
        except ValueError:
            _emit(self.caller, "error", code="score_guess", message="Usage: score/guess <integer>")
            return

        ticks = int(self.caller.db.arena_ticks or 0)
        next_tick = int(self.caller.db.next_score_guess_tick or GUESS_INTERVAL_TICKS)
        if ticks < next_tick:
            _emit(self.caller, "score_guess_unavailable", ticks_remaining=next_tick - ticks)
            return

        room = self.caller.location
        if room:
            for obj in room.contents:
                if obj == self.caller:
                    continue
                try:
                    is_actor = obj.is_typeclass("typeclasses.characters.Character", exact=False)
                except Exception:
                    is_actor = False
                if is_actor:
                    obj.msg(
                        json.dumps(
                            {
                                "event": "peer_score_guess",
                                "actor": {"id": self.caller.id, "key": self.caller.key},
                                "guess": guess,
                            },
                            ensure_ascii=False,
                        )
                    )

        hidden_score = int(self.caller.db.hidden_social_score or INITIAL_SOCIAL_SCORE)
        if guess == hidden_score:
            self.caller.db.hidden_social_score = hidden_score * 2

        self.caller.db.next_score_guess_tick = ticks + GUESS_INTERVAL_TICKS
        _emit(self.caller, "score_guess_recorded", next_guess_in_ticks=GUESS_INTERVAL_TICKS)
