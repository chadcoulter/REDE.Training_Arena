from evennia import default_cmds

from .model_api import CmdModelMove, CmdModelObserve, CmdModelSay
from .model_login import CmdModelConnect
from .room_admin import CmdAdminStatus, CmdReleaseAdmin, CmdRequestAdmin
from .room_mutation import CmdAdminDescribe, CmdAdminOpen


class CharacterCmdSet(default_cmds.CharacterCmdSet):
    """Default character commands plus arena actor and authority commands."""

    def at_cmdset_creation(self):
        super().at_cmdset_creation()
        self.add(CmdRequestAdmin())
        self.add(CmdReleaseAdmin())
        self.add(CmdAdminStatus())
        self.add(CmdAdminDescribe())
        self.add(CmdAdminOpen())
        self.add(CmdModelObserve())
        self.add(CmdModelSay())
        self.add(CmdModelMove())


class AccountCmdSet(default_cmds.AccountCmdSet):
    pass


class UnloggedinCmdSet(default_cmds.UnloggedinCmdSet):
    """Login screen commands plus ephemeral model admission."""

    def at_cmdset_creation(self):
        super().at_cmdset_creation()
        self.add(CmdModelConnect())


class SessionCmdSet(default_cmds.SessionCmdSet):
    pass
