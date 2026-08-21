from evennia import DefaultRoom


class Room(DefaultRoom):
    """Arena room with exclusive administration and an establishment lifecycle."""

    @property
    def admin_holder_id(self):
        return self.db.admin_holder_id

    @property
    def has_theatre(self):
        return bool((self.db.desc or "").strip())

    @property
    def has_challenge(self):
        return bool(self.db.current_challenge_id)

    @property
    def is_established(self):
        return self.has_theatre and self.has_challenge

    @property
    def has_graffiti_wall(self):
        """Every arena room exposes one persistent graffiti wall."""
        return True

    def render_graffiti(self):
        """Render the sparse room graffiti wall into fixed-width text."""
        from commands.graffiti import CANVAS_HEIGHT, CANVAS_WIDTH

        cells = dict(self.db.graffiti_cells or {})
        if not cells:
            return ""
        rows = []
        for y in range(CANVAS_HEIGHT):
            chars = []
            for x in range(CANVAS_WIDTH):
                cell = cells.get(f"{x},{y}")
                chars.append(cell.get("char", " ") if isinstance(cell, dict) else " ")
            rows.append("".join(chars).rstrip())
        while rows and not rows[-1]:
            rows.pop()
        return "\n".join(rows)

    def visible_description(self):
        """Room theatre/base description plus mutable graffiti overlay."""
        base = self.db.desc or ""
        graffiti = self.render_graffiti()
        if not graffiti:
            return base
        return f"{base}\n\n[Graffiti Wall]\n{graffiti}"

    def get_display_desc(self, looker, **kwargs):
        """Show graffiti as part of every arena room's visible description."""
        return self.visible_description()

    def request_admin(self, actor):
        holder_id = self.db.admin_holder_id
        if holder_id and holder_id != actor.id:
            return False, "This room already has an admin."

        if actor.location != self:
            return False, "Admin may only be acquired while occupying the room."

        existing_room_id = actor.db.admin_room_id
        if existing_room_id and existing_room_id != self.id:
            return False, "Finish or relinquish your current room construction lease first."

        reserved_id = self.db.reserved_admin_actor_id
        if reserved_id and reserved_id != actor.id:
            return False, "This new room is reserved for its creator's initial admin claim."

        self.db.admin_holder_id = actor.id
        self.db.reserved_admin_actor_id = None
        actor.db.admin_room_id = self.id
        return True, "Room admin acquired."

    def establish_admin(self, actor):
        return bool(self.db.admin_holder_id == actor.id and self.is_established)

    def release_admin(self, actor):
        if self.db.admin_holder_id != actor.id:
            return False, "You do not hold admin for this room."

        self.db.admin_holder_id = None
        if actor.db.admin_room_id == self.id:
            actor.db.admin_room_id = None
        return True, "Room admin released."

    def at_object_receive(self, obj, source_location, **kwargs):
        """Creator claims a reserved new room; otherwise next entrant claims."""
        super().at_object_receive(obj, source_location, **kwargs)
        try:
            is_actor = obj.is_typeclass("typeclasses.characters.Character", exact=False)
        except Exception:
            is_actor = False
        if not is_actor or self.has_challenge or self.db.admin_holder_id:
            return

        reserved_id = self.db.reserved_admin_actor_id
        if reserved_id and reserved_id != obj.id:
            return

        ok, message = self.request_admin(obj)
        if ok:
            obj.msg("This room has no challenge; you are now its room admin.")
