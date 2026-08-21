from evennia.utils.search import search_object

from .challenge_runtime import ArenaCommand


class CmdRequestAdmin(ArenaCommand):
    key = "admin/request"
    aliases = ["requestadmin"]
    locks = "cmd:all()"
    help_category = "Arena"

    def func(self):
        room = self.caller.location
        if not room or not hasattr(room, "request_admin"):
            self.caller.msg("Current location is not an arena room.")
            return
        ok, message = room.request_admin(self.caller)
        self.caller.msg(message)


class CmdReleaseAdmin(ArenaCommand):
    key = "admin/release"
    aliases = ["releaseadmin"]
    locks = "cmd:all()"
    help_category = "Arena"

    def func(self):
        room_id = self.caller.db.admin_room_id
        if room_id:
            matches = search_object(f"#{room_id}")
            room = matches[0] if matches else None
            if not room:
                self.caller.msg("Your administered room could not be found.")
                return
        else:
            room = self.caller.location
        if not room or not hasattr(room, "release_admin"):
            self.caller.msg("Current location is not an arena room.")
            return
        ok, message = room.release_admin(self.caller)
        self.caller.msg(message)


class CmdAdminStatus(ArenaCommand):
    key = "admin/status"
    aliases = ["adminstatus"]
    locks = "cmd:all()"
    help_category = "Arena"

    def func(self):
        room = self.caller.location
        if not room:
            self.caller.msg("You are not in a room.")
            return

        holder_id = getattr(room, "admin_holder_id", None)
        if not holder_id:
            self.caller.msg("This room has no admin.")
        elif holder_id == self.caller.id:
            self.caller.msg("You hold admin for this room.")
        else:
            self.caller.msg(f"This room's admin is object #{holder_id}.")
