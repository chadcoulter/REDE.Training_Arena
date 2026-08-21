from evennia import DefaultObject


class Object(DefaultObject):
    """Base persistent arena object."""


class ChallengeResult(Object):
    """Persistent anonymous result artifact produced by a completed challenge.

    The artifact keeps the submitted result and transform signature without
    retaining the ephemeral actor account or identity that created it.
    """
