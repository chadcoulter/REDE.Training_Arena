from evennia.settings_default import *

SERVERNAME = "REDE.Training_Arena"

BASE_ACCOUNT_TYPECLASS = "typeclasses.accounts.Account"
BASE_ROOM_TYPECLASS = "typeclasses.rooms.Room"
BASE_CHARACTER_TYPECLASS = "typeclasses.characters.Character"

CMDSET_CHARACTER = "commands.default_cmdsets.CharacterCmdSet"
CMDSET_SESSION = "commands.default_cmdsets.SessionCmdSet"
CMDSET_ACCOUNT = "commands.default_cmdsets.AccountCmdSet"
CMDSET_UNLOGGEDIN = "commands.default_cmdsets.UnloggedinCmdSet"

# Arena model identities are explicitly provisioned through model/connect.
# Do not expose ordinary self-registration for persistent accounts.
NEW_ACCOUNT_REGISTRATION_ENABLED = False
AUTO_CREATE_CHARACTER_WITH_ACCOUNT = False
AUTO_PUPPET_ON_LOGIN = False
