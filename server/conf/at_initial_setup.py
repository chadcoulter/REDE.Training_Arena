from evennia import create_object

ROOM = "typeclasses.rooms.Room"
EXIT = "typeclasses.exits.Exit"


def _room(key, desc):
    room = create_object(ROOM, key=key)
    room.db.desc = desc
    return room


def _link(source, key, destination, aliases=None):
    return create_object(
        EXIT,
        key=key,
        aliases=aliases or [],
        location=source,
        destination=destination,
    )


def at_initial_setup():
    """Create the small, stable core of the Training Arena exactly once."""
    lobby = _room(
        "Arena Lobby",
        "Neutral arrival space. Participants enter as ordinary actors and may observe, communicate, and choose where to work.",
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

    _link(lobby, "observation", observation, ["observe"])
    _link(observation, "lobby", lobby)
    _link(observation, "training", training, ["train"])
    _link(training, "observation", observation, ["observe"])
    _link(training, "sandbox", sandbox)
    _link(sandbox, "training", training, ["train"])

    # Evennia's initial Limbo remains available to operators; new characters
    # are explicitly pointed at the Arena Lobby for the normal arena path.
    from django.conf import settings

    settings.START_LOCATION = lobby.id
    settings.DEFAULT_HOME = lobby.id
