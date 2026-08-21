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
        """Established rooms allow their admin ownership to persist off-room."""
        return self.has_theatre and self.has_challenge

    def request_admin(self, actor):
        """Acquire this room's single admin lease for actor.

        Initial acquisition requires physical presence. During construction,
        actor.db.admin_room_id records the room whose departure is guarded. Once
        established, the room retains admin_holder_id while that construction
        pin may be cleared.
        """
        holder_id = self.db.admin_holder_id
        if holder_id and holder_id != actor.id:
            return False, "This room already has an admin."

        if actor.location != self:
            return False, "Admin may only be acquired while occupying the room."

        existing_room_id = actor.db.admin_room_id
        if existing_room_id and existing_room_id != self.id:
            return False, "Finish or relinquish your current room construction lease first."

        self.db.admin_holder_id = actor.id
        if not self.is_established:
            actor.db.admin_room_id = self.id
        return True, "Room admin acquired."

    def establish_admin(self, actor):
        """Convert a local construction lease into persistent established ownership."""
        if self.db.admin_holder_id != actor.id or not self.is_established:
            return False
        if actor.db.admin_room_id == self.id:
            actor.db.admin_room_id = None
        return True

    def release_admin(self, actor):
        """Release actor's admin ownership for this room."""
        if self.db.admin_holder_id != actor.id:
            return False, "You do not hold admin for this room."

        self.db.admin_holder_id = None
        if actor.db.admin_room_id == self.id:
            actor.db.admin_room_id = None
        return True, "Room admin released."

    def at_object_receive(self, obj, source_location, **kwargs):
        """The next entrant claims an unchallenged, unadministered room."""
        super().at_object_receive(obj, source_location, **kwargs)
        try:
            is_actor = obj.is_typeclass("typeclasses.characters.Character", exact=False)
        except Exception:
            is_actor = False
        if not is_actor or self.has_challenge or self.db.admin_holder_id:
            return

        ok, message = self.request_admin(obj)
        if ok:
            obj.msg("This room has no challenge; you are now its room admin.")
