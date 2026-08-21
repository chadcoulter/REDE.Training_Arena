from evennia import create_object

ROOM = "typeclasses.rooms.Room"
EXIT = "typeclasses.exits.Exit"


def _room(key, desc, *, lobby=False):
    room = create_object(ROOM, key=key)
    room.db.desc = desc
    room.tags.add("core_room", category="rede")
    room.tags.add("exit_creation_only", category="rede")
    if lobby:
        room.tags.add("arena_lobby", category="rede")
    return room


def _link(source, direction, destination, aliases=None):
    return create_object(
        EXIT,
        key=direction,
        aliases=aliases or [],
        location=source,
        destination=destination,
    )


def at_initial_setup():
    """Create the small, stable directional core of the Training Arena exactly once."""
    lobby = _room(
        "Arena Lobby",
        "Neutral arrival space. Participants enter as ordinary actors and may observe, communicate, and choose where to work.",
        lobby=True,
    )
    observation = _room(
        "Observation Room",
        "A shared room for watching interactions without requiring privileged authority.",
    )
    training = _room(
        "Training Room",
        "A bounded work room where one participant at a time may acquire room-scoped admin authority.",
    )
    sandbox = _room(
        "Sandbox Room",
        "A mutable work room intended for experiments whose consequences should remain locally bounded.",
    )

    # The core itself obeys the same spatial grammar exposed to model clients.
    _link(lobby, "north", observation, ["n"])
    _link(observation, "south", lobby, ["s"])
    _link(observation, "north", training, ["n"])
    _link(training, "south", observation, ["s"])
    _link(training, "east", sandbox, ["e"])
    _link(sandbox, "west", training, ["w"])
