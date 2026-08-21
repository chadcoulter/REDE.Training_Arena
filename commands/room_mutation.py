from evennia import Command, create_object

EXIT = "typeclasses.exits.Exit"


def _require_admin(caller):
    room = caller.location
    if not room or room.db.admin_holder_id != caller.id:
        caller.msg("Room admin is required for this mutation.")
        return None
    return room


class CmdAdminDescribe(Command):
    """Replace the description of the room currently administered."""

    key = "admin/describe"
    locks = "cmd:all()"
    help_category = "Arena Admin"

    def func(self):
        room = _require_admin(self.caller)
        if not room:
            return
        text = self.args.strip()
        if not text:
            self.caller.msg("Usage: admin/describe <description>")
            return
        room.db.desc = text
        self.caller.msg("Room description updated.")


class CmdAdminOpen(Command):
    """Open a one-way exit from the administered room to another arena room."""

    key = "admin/open"
    locks = "cmd:all()"
    help_category = "Arena Admin"

    def func(self):
        room = _require_admin(self.caller)
        if not room:
            return
        if "=" not in self.args:
            self.caller.msg("Usage: admin/open <exit name>=<destination room>")
            return

        exit_name, destination_name = (part.strip() for part in self.args.split("=", 1))
        if not exit_name or not destination_name:
            self.caller.msg("Both an exit name and destination are required.")
            return

        destination = self.caller.search(destination_name, global_search=True)
        if not destination:
            return
        if not hasattr(destination, "request_admin"):
            self.caller.msg("Destination must be an arena Room.")
            return
        if any(obj.key.lower() == exit_name.lower() for obj in room.exits):
            self.caller.msg("An exit with that name already exists in this room.")
            return

        created = create_object(EXIT, key=exit_name, location=room, destination=destination)
        self.caller.msg(
            f"Opened one-way exit '{created.key}' from {room.key} to {destination.key}. "
            "Creating a return exit requires admin authority in the destination room."
        )
