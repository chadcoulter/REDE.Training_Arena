from evennia import DefaultObject


class Object(DefaultObject):
    """Base persistent arena object."""


class RoomArtifact(Object):
    """One actor-authored persistent object in one room.

    Arena actors are ephemeral, but artifacts are world state. The creator is
    linked by an anonymous actor token rather than by account credentials or a
    persistent user record.
    """

    def at_object_creation(self):
        super().at_object_creation()
        self.tags.add("room_artifact", category="arena")
        self.db.decoration = {}
        self.db.challenge_results = {}
        self.db.challenge_id = None
        self.db.transform_signature = None
        self.db.transform_key = None
        self.db.reviewed = False
        self.db.steps = None
        self.db.awarded_xp = 0
        self.locks.add("get:false();drop:false();puppet:false()")
