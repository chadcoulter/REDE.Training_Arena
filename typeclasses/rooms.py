from evennia import DefaultRoom


class Room(DefaultRoom):
    """Arena room with exclusive administration and an establishment lifecycle."""

    @property
    def admin_holder_id(self):
        return self.db.admin_holder_id

    @property
    def has_theatre(self):
        """A non-empty room description establishes the challenge theatre."""
        return bool((self.db.desc or "").strip())

    @property
    def has_challenge(self):
        """True once the room has a currently published challenge."""
        return bool(self.db.current_challenge_id)

    @property
    def is_established(self):
        """Established rooms allow their admin lease to persist off-room."""
        return self.has_theatre and self.has_challenge

    def request_admin(self, actor):
        """Acquire this room's single admin lease for actor.

        Initial acquisition still requires physical presence. Once the room is
        established, the lease may remain with the actor after it leaves.
        """
        holder_id = self.db.admin_holder_id
        if holder_id and holder_id != actor.id:
            return False, "This room already has an admin."

        if actor.location != self:
            return False, "Admin may only be acquired while occupying the room."

        existing_room_id = actor.db.admin_room_id
        if existing_room_id and existing_room_id != self.id:
            return False, "Release your existing room admin lease first."

        self.db.admin_holder_id = actor.id
        actor.db.admin_room_id = self.id
        return True, "Room admin acquired."

    def release_admin(self, actor):
        """Release actor's admin lease for this room."""
        if self.db.admin_holder_id != actor.id:
            return False, "You do not hold admin for this room."

        self.db.admin_holder_id = None
        if actor.db.admin_room_id == self.id:
            actor.db.admin_room_id = None
        return True, "Room admin released."
