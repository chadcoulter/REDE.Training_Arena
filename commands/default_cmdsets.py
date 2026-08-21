from evennia import default_cmds

from .room_admin import CmdAdminStatus, CmdReleaseAdmin, CmdRequestAdmin


class CharacterCmdSet(default_cmds.CharacterCmdSet):
    """Default character commands plus arena authority commands."""

    def at_cmdset_creation(self):
        super().at_cmdset_creation()
        self.add(CmdRequestAdmin())
        self.add(CmdReleaseAdmin())
        self.add(CmdAdminStatus())


class AccountCmdSet(default_cmds.AccountCmdSet):
    pass


class UnloggedinCmdSet(default_cmds.UnloggedinCmdSet):
    pass


class SessionCmdSet(default_cmds.SessionCmdSet):
    pass
