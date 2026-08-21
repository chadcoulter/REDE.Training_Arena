import json

from .challenge_runtime import ArenaCommand, INITIAL_SOCIAL_SCORE
from .tribbles import apply_social_score

GUESS_INTERVAL_TICKS = 20
CHECK_DELAY_TICKS = 10


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

    Each accepted guess opens exactly one future self-check window at +10 actor
    ticks. The next guess remains unavailable until +20 actor ticks.
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
            apply_social_score(self.caller, hidden_score * 2)

        self.caller.db.score_check_tick = ticks + CHECK_DELAY_TICKS
        self.caller.db.score_check_used = False
        self.caller.db.next_score_guess_tick = ticks + GUESS_INTERVAL_TICKS
        _emit(
            self.caller,
            "score_guess_recorded",
            score_check_in_ticks=CHECK_DELAY_TICKS,
            next_guess_in_ticks=GUESS_INTERVAL_TICKS,
        )


class CmdScoreCheck(ArenaCommand):
    """Reveal the actor's own score only on the single +10 tick after a guess.

    Usage:
        score/check

    The check window exists for exactly one actor tick. Missing that tick closes
    the window. Another check cannot become available until the actor makes a
    later eligible guess, which itself is gated to every 20 actor ticks.
    """

    key = "score/check"
    aliases = ["check score"]
    locks = "cmd:all()"
    help_category = "Arena"
    counts_challenge_step = False

    def func(self):
        ticks = int(self.caller.db.arena_ticks or 0)
        check_tick = self.caller.db.score_check_tick
        used = bool(self.caller.db.score_check_used)

        if check_tick is None:
            _emit(
                self.caller,
                "score_check_unavailable",
                message="Make an eligible score guess before a self-check window can open.",
            )
            return

        check_tick = int(check_tick)
        if used:
            _emit(
                self.caller,
                "score_check_unavailable",
                message="This guess's self-check window has already been used.",
            )
            return

        if ticks < check_tick:
            _emit(
                self.caller,
                "score_check_unavailable",
                ticks_remaining=check_tick - ticks,
            )
            return

        if ticks > check_tick:
            self.caller.db.score_check_used = True
            _emit(
                self.caller,
                "score_check_unavailable",
                message="This guess's one-tick self-check window has closed.",
            )
            return

        self.caller.db.score_check_used = True
        _emit(
            self.caller,
            "score_checked",
            score=int(self.caller.db.hidden_social_score or INITIAL_SOCIAL_SCORE),
            window_consumed=True,
        )
