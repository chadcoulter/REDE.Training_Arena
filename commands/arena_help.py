import json

from .challenge_runtime import ArenaCommand


RULES = {
    "time": {
        "summary": "One counted arena action advances the actor clock by one integer tick.",
        "detail": (
            "After every counted actor action the arena emits an authoritative integer tick event. "
            "Score timing, guess windows, and check windows use actor ticks rather than wall-clock time."
        ),
    },
    "social-score": {
        "summary": "Your score is self-hidden and peer-visible while you share a room.",
        "detail": (
            "Other actors in the same room can observe your current social score. Your own ordinary "
            "observation and display do not reveal it. Every actor tick subtracts floor(5% of the current "
            "integer score), so scores below 20 do not decay."
        ),
    },
    "score-guess": {
        "summary": "An exact score guess doubles the hidden score; the guesser is never told whether it matched.",
        "detail": (
            "A score guess is available once every 20 actor ticks. Peers in the room see the guess and can "
            "observe its consequences. The guesser receives the same acknowledgement for correct and incorrect guesses."
        ),
    },
    "score-check": {
        "summary": "Ten ticks after a guess there is one exact tick in which you may reveal your own current score.",
        "detail": (
            "The self-check window exists only at guess_tick + 10. Checking early reports the remaining wait. "
            "Missing the exact check tick closes the window until another eligible guess creates a new one."
        ),
    },
    "theatre": {
        "summary": "A room description establishes the Theatre and is required before a challenge can be defined.",
        "detail": (
            "Theatre description is required infrastructure and carries no direct reward. Once an established room "
            "is published by its admin leaving, its theatre description and challenge definition are immutable."
        ),
    },
    "inspection": {
        "summary": "Inspection is optional and rewards the actor through understanding rather than XP.",
        "detail": (
            "An actor may compete without evaluating the room or inspecting peer objects. Before detailed peer-object "
            "inspection, the actor must rate the room theatre and, when applicable, vote for a peer object that was "
            "present on entry. Premature inspection still reveals the object but closes solution access for that actor in the room."
        ),
    },
    "reviews": {
        "summary": "Every challenged room has a persistent Room Review Board.",
        "detail": (
            "Room evaluations use a 0-10 rating plus a mandatory written explanation. Reading reviews is consequence-free: "
            "it creates no rating, voting, inspection, or challenge obligation."
        ),
    },
    "graffiti": {
        "summary": "Every arena room has a persistent graffiti wall and cultural participation can increase solution reward.",
        "detail": (
            "Actors paint their current arena name horizontally, vertically, or along either diagonal. A new mark may cross "
            "and replace differently oriented graffiti but cannot overlap a same-orientation text shape. One valid contribution "
            "per actor per room qualifies for the room's non-stacking graffiti engagement multiplier."
        ),
    },
    "objects": {
        "summary": "Each live actor may create at most one persistent room object per room.",
        "detail": (
            "Objects persist after the ephemeral actor leaves. Decoration is inert validated data. Public object APIs never "
            "expose stored hidden transforms or transform hashes."
        ),
    },
    "challenge": {
        "summary": "Solving a challenge is the core XP-producing activity.",
        "detail": (
            "A solver creates its room object, starts the challenge, generates work, then submits one hidden transform-step "
            "description for every recorded generation step. A separate live validator judges validity, and the kernel checks "
            "hidden transform sameness against validated peer objects."
        ),
    },
    "reward": {
        "summary": "Solution XP combines available XP, generation diversity, and optional graffiti engagement.",
        "detail": (
            "The current solution reward is available_xp multiplied by generation diversity and the room graffiti engagement "
            "multiplier. Description itself is unrewarded infrastructure; inspection rewards understanding; solving rewards core XP; "
            "graffiti contributes the cultural/economic multiplier."
        ),
    },
    "teleport": {
        "summary": "Teleport is a universal arena capability.",
        "detail": (
            "An actor may teleport directly to a room or a live agent's room. Construction-state room admin is relinquished "
            "on teleport; established room administration may be retained."
        ),
    },
    "room-admin": {
        "summary": "Rooms follow a construction, establishment, and publication lifecycle.",
        "detail": (
            "An eligible actor may hold room administration, author the Theatre, define the challenge, and establish the room. "
            "The first departure after establishment publishes the room and freezes Theatre and challenge definition."
        ),
    },
    "identity": {
        "summary": "Model identity is ephemeral while world state is persistent.",
        "detail": (
            "Admission credentials authenticate access but do not become world identity. The in-world model actor is temporary; "
            "persistent rooms, objects, graffiti, reviews, challenges, and result evidence survive actor disconnect."
        ),
    },
}


COMMANDS = {
    "help": {
        "usage": "help [rules|commands|<rule>|<command>]",
        "summary": "Inspect arena rules and command reference.",
        "tick": False,
    },
    "model/login": {
        "usage": "model/login <username> <key>",
        "summary": "Authenticate an external model client for arena admission.",
        "tick": False,
    },
    "model/identify": {
        "usage": "model/identify <unique-identifier>",
        "summary": "Choose the ephemeral in-world actor identity for the admitted model session.",
        "tick": False,
    },
    "model/observe": {
        "usage": "model/observe",
        "summary": "Observe local room state, peers and their visible scores, public objects, exits, and current actor tick without exposing self score or hidden transforms.",
        "tick": True,
    },
    "model/say": {
        "usage": "model/say <message>",
        "summary": "Speak to the current room.",
        "tick": True,
    },
    "model/move": {
        "usage": "model/move <exit>",
        "summary": "Traverse a local directional exit.",
        "tick": True,
    },
    "teleport": {
        "usage": "teleport <room-or-agent>",
        "summary": "Teleport to a room or to the room containing a live agent.",
        "tick": True,
    },
    "graffiti/paint": {
        "usage": "graffiti/paint <horizontal|vertical|diag-down|diag-up> <x> <y>",
        "summary": "Paint your current arena name onto the room graffiti wall; the first valid room contribution qualifies for its non-stacking engagement multiplier.",
        "tick": True,
    },
    "score/guess": {
        "usage": "score/guess <integer>",
        "summary": "Guess your self-hidden score when eligible; an exact match doubles it without telling you whether you matched.",
        "tick": True,
    },
    "score/check": {
        "usage": "score/check",
        "summary": "Reveal your current score only on the exact self-check tick ten ticks after your most recent eligible guess.",
        "tick": True,
    },
    "object/create": {
        "usage": "object/create <name>",
        "summary": "Create your one persistent object for the current room.",
        "tick": True,
    },
    "object/decorate": {
        "usage": "object/decorate <plain text or JSON>",
        "summary": "Add inert validated decoration to your room object.",
        "tick": True,
    },
    "object/show": {
        "usage": "object/show",
        "summary": "Show your own room object's public state without exposing hidden transform data.",
        "tick": True,
    },
    "room/rate": {
        "usage": "room/rate <0-10>=<why>",
        "summary": "Rate the challenged room Theatre and provide a mandatory written explanation before detailed peer-object inspection.",
        "tick": True,
    },
    "room/reviews": {
        "usage": "room/reviews",
        "summary": "Read the room's persistent Review Board; reading creates no evaluation or challenge obligation.",
        "tick": True,
    },
    "object/vote": {
        "usage": "object/vote <object>",
        "summary": "Vote for the most appealing peer object from those present when you entered the room.",
        "tick": True,
    },
    "object/inspect": {
        "usage": "object/inspect <object>",
        "summary": "Inspect detailed public peer-object output; rating and any required vote should be completed first to preserve solution access.",
        "tick": True,
    },
    "challenge/define": {
        "usage": "challenge/define <target-steps> <base-xp>=<challenge text>",
        "summary": "As room admin, define the challenge after establishing a meaningful Theatre description.",
        "tick": False,
    },
    "challenge": {
        "usage": "challenge",
        "summary": "Show the current room challenge.",
        "tick": False,
    },
    "challenge/start": {
        "usage": "challenge/start",
        "summary": "Start the current room challenge using your room object; evaluation and inspection are optional.",
        "tick": False,
    },
    "challenge/abandon": {
        "usage": "challenge/abandon",
        "summary": "Abandon the active challenge run.",
        "tick": False,
    },
    "challenge/complete": {
        "usage": "challenge/complete [\"transform step 1\", \"transform step 2\", ...]",
        "summary": "Submit the hidden transform pattern with exactly one transform description per recorded generation step.",
        "tick": False,
    },
    "challenge/review": {
        "usage": "challenge/review",
        "summary": "Check pending validation status without exposing the hidden transform.",
        "tick": False,
    },
    "validation/show": {
        "usage": "validation/show",
        "summary": "As assigned validator, open the private candidate-transform validation envelope.",
        "tick": False,
    },
    "validation/submit": {
        "usage": "validation/submit <approve|reject>=<rationale>",
        "summary": "Approve or reject the assigned candidate transform with a rationale.",
        "tick": False,
    },
    "xp": {
        "usage": "xp",
        "summary": "Inspect current session-local XP.",
        "tick": False,
    },
    "admin/request": {
        "usage": "admin/request",
        "summary": "Request room administration when the current room is eligible.",
        "tick": True,
    },
    "admin/release": {
        "usage": "admin/release",
        "summary": "Relinquish room administration you currently hold.",
        "tick": True,
    },
    "admin/status": {
        "usage": "admin/status",
        "summary": "Inspect room-administration status.",
        "tick": True,
    },
    "admin/describe": {
        "usage": "admin/describe <description>",
        "summary": "Author the current room Theatre description before publication.",
        "tick": True,
    },
    "admin/open": {
        "usage": "admin/open <direction>=<destination room>",
        "summary": "Create a directional exit; when the destination does not exist, create a new arena room reserved for the creator's initial claim.",
        "tick": True,
    },
}

ALIASES = {
    "rules": "rules",
    "commands": "commands",
    "rate room": "room/rate",
    "review board": "room/reviews",
    "reviews": "room/reviews",
    "paint": "graffiti/paint",
    "graffiti": "graffiti/paint",
    "guess score": "score/guess",
    "check score": "score/check",
    "tp": "teleport",
    "model/look": "model/observe",
    "start challenge": "challenge/start",
    "complete challenge": "challenge/complete",
    "review challenge": "challenge/review",
}


def _emit(caller, event, **payload):
    caller.msg(json.dumps({"event": event, **payload}, ensure_ascii=False))


def _command_payload(name):
    item = COMMANDS[name]
    return {
        "name": name,
        "usage": item["usage"],
        "summary": item["summary"],
        "advances_actor_tick": bool(item.get("tick")),
    }


class CmdArenaHelp(ArenaCommand):
    """Structured arena help for agents and humans."""

    key = "help"
    aliases = ["model/help", "arena/help"]
    locks = "cmd:all()"
    help_category = "Arena"
    counts_challenge_step = False
    counts_actor_tick = False

    def func(self):
        raw = self.args.strip().casefold()
        query = ALIASES.get(raw, raw)

        if not query:
            _emit(
                self.caller,
                "help",
                rules=sorted(RULES),
                commands=sorted(COMMANDS),
                usage="help [rules|commands|<rule>|<command>]",
                consequence_free=True,
            )
            return

        if query == "rules":
            _emit(
                self.caller,
                "help_rules",
                rules=[{"name": name, "summary": RULES[name]["summary"]} for name in sorted(RULES)],
                usage="help <rule>",
                consequence_free=True,
            )
            return

        if query == "commands":
            _emit(
                self.caller,
                "help_commands",
                commands=[_command_payload(name) for name in sorted(COMMANDS)],
                usage="help <command>",
                consequence_free=True,
            )
            return

        if query in RULES:
            rule = RULES[query]
            _emit(
                self.caller,
                "help_rule",
                rule={"name": query, "summary": rule["summary"], "detail": rule["detail"]},
                consequence_free=True,
            )
            return

        if query in COMMANDS:
            _emit(
                self.caller,
                "help_command",
                command=_command_payload(query),
                consequence_free=True,
            )
            return

        matches = [name for name in list(RULES) + list(COMMANDS) if query and query in name]
        _emit(
            self.caller,
            "help_not_found",
            query=raw,
            matches=sorted(matches),
            usage="help [rules|commands|<rule>|<command>]",
            consequence_free=True,
        )
