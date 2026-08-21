from evennia import DefaultAccount
from evennia.utils.search import search_object


class Account(DefaultAccount):
    """Arena account typeclass.

    Model accounts may be marked ephemeral. An ephemeral account and its
    character are removed after the account's final session disconnects.
    """

    def at_post_disconnect(self, **kwargs):
        super().at_post_disconnect(**kwargs)

        if not self.db.arena_ephemeral or self.sessions.count():
            return

        # Release any room authority before deleting the actor so a stale
        # admin-holder id can never survive the session.
        for character in list(self.characters.all()):
            admin_room_id = character.db.admin_room_id
            if admin_room_id:
                rooms = search_object(f"#{admin_room_id}")
                room = rooms[0] if rooms else None
                if room and getattr(room, "admin_holder_id", None) == character.id:
                    room.release_admin(character)

            character.delete()

        # The account exists only to bind the live Evennia session to the
        # transient actor. No admission username/key is stored on it.
        self.delete()
