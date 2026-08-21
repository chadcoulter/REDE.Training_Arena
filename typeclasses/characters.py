from uuid import uuid4

from evennia import DefaultCharacter, search_object


class Character(DefaultCharacter):
    """Arena participant. Admin authority pins the actor to its current room."""

    def at_object_creation(self):
        super().at_object_creation()
        self.db.arena_actor_token = uuid4().hex
        self.db.xp = 0
        self.db.active_challenge = None
        self.db.pending_challenge_review = None

        lobbies = search_object("Arena Lobby", exact=True)
        lobby = next((obj for obj in lobbies if obj.tags.has("arena_lobby", category="rede")), None)
        if lobby:
            self.home = lobby
            self.location = lobby

    def at_pre_move(self, destination, **kwargs):
        if self.db.admin_room_id:
            self.msg("Release room admin before moving.")
            return False
        return super().at_pre_move(destination, **kwargs)
