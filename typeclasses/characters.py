from evennia import DefaultCharacter


class Character(DefaultCharacter):
    """Arena participant. Admin authority pins the actor to its current room."""

    def at_pre_move(self, destination, **kwargs):
        if self.db.admin_room_id:
            self.msg("Release room admin before moving.")
            return False
        return super().at_pre_move(destination, **kwargs)
