from evennia import default_cmds

from .artifacts import CmdObjectCreate, CmdObjectDecorate, CmdObjectShow
from .challenges import (
    CmdChallengeAbandon,
    CmdChallengeShow,
    CmdXP,
)
from .graffiti import CmdGraffitiPaint
from .hidden_challenges import (
    CmdChallengeCompleteHidden,
    CmdChallengeReviewHidden,
    CmdChallengeStartHidden,
    CmdValidationShow,
    CmdValidationSubmit,
)
from .model_api import CmdModelMove, CmdModelObserve, CmdModelSay, CmdTeleport
from .model_login import CmdModelIdentify, CmdModelLogin
from .room_admin import CmdAdminStatus, CmdReleaseAdmin, CmdRequestAdmin
from .room_challenge import CmdChallengeDefinePublished
from .room_mutation import CmdAdminDescribe, CmdAdminOpen
from .room_review import CmdObjectInspect, CmdObjectVote, CmdRoomRate, CmdRoomReviews
from .score import CmdScoreCheck, CmdScoreGuess


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
        self.add(CmdTeleport())
        self.add(CmdGraffitiPaint())
        self.add(CmdScoreGuess())
        self.add(CmdScoreCheck())
        self.add(CmdObjectCreate())
        self.add(CmdObjectDecorate())
        self.add(CmdObjectShow())
        self.add(CmdRoomRate())
        self.add(CmdRoomReviews())
        self.add(CmdObjectVote())
        self.add(CmdObjectInspect())
        self.add(CmdChallengeDefinePublished())
        self.add(CmdChallengeShow())
        self.add(CmdChallengeStartHidden())
        self.add(CmdChallengeAbandon())
        self.add(CmdChallengeCompleteHidden())
        self.add(CmdChallengeReviewHidden())
        self.add(CmdValidationShow())
        self.add(CmdValidationSubmit())
        self.add(CmdXP())


class AccountCmdSet(default_cmds.AccountCmdSet):
    pass


class UnloggedinCmdSet(default_cmds.UnloggedinCmdSet):
    """Login screen commands plus ephemeral model admission."""

    def at_cmdset_creation(self):
        super().at_cmdset_creation()
        self.add(CmdModelLogin())
        self.add(CmdModelIdentify())


class SessionCmdSet(default_cmds.SessionCmdSet):
    pass
