from evennia import DefaultRoom


class Room(DefaultRoom):
    """A room is the authority boundary for privileged model work."""

    @property
    def admin_holder_id(self):
        return self.db.admin_holder_id

    def request_admin(self, actor):
        """Acquire this room's single admin lease for actor."""
        holder_id = self.db.admin_holder_id
        if holder_id and holder_id != actor.id:
            return False, "This room already has an admin."

        if actor.location != self:
            return False, "Admin may only be acquired for the room you occupy."

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
