from uuid import uuid4

from evennia import DefaultCharacter, search_object


class Character(DefaultCharacter):
    """Arena participant with ephemeral identity and room-admin lifecycle."""

    def at_object_creation(self):
        super().at_object_creation()
        self.db.arena_actor_token = uuid4().hex
        self.db.xp = 0
        self.db.active_challenge = None
        self.db.pending_challenge_review = None
        self.db.solution_closed_rooms = []
        self.db.room_visit = None
        self.db.pending_admin_exit = None

        lobbies = search_object("Arena Lobby", exact=True)
        lobby = next((obj for obj in lobbies if obj.tags.has("arena_lobby", category="rede")), None)
        if lobby:
            self.home = lobby
            self.location = lobby
            from commands.challenge_runtime import prepare_room_visit

            prepare_room_visit(self, lobby)

    def _admin_room(self):
        room_id = self.db.admin_room_id
        if not room_id:
            return None
        matches = search_object(f"#{room_id}")
        return matches[0] if matches else None

    def at_pre_move(self, destination, **kwargs):
        admin_room = self._admin_room()
        if admin_room and admin_room.db.admin_holder_id == self.id:
            if admin_room.is_established:
                # Established-room administration is allowed to persist remotely.
                return super().at_pre_move(destination, **kwargs)

            # During construction, directional movement requires an explicit
            # second attempt to confirm abandonment and lease release.
            pending = self.db.pending_admin_exit
            if not isinstance(pending, dict) or pending.get("destination_id") != destination.id:
                self.db.pending_admin_exit = {"destination_id": destination.id}
                self.msg(
                    "This room is not yet established. Moving will relinquish room admin. "
                    "Repeat the move to confirm."
                )
                return False

            admin_room.release_admin(self)
            self.db.pending_admin_exit = None

        return super().at_pre_move(destination, **kwargs)

    def at_post_move(self, source_location, **kwargs):
        super().at_post_move(source_location, **kwargs)
        self.db.pending_admin_exit = None
        from commands.challenge_runtime import prepare_room_visit

        prepare_room_visit(self, self.location)
