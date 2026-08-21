import os

import dj_database_url
from evennia.settings_default import *

SERVERNAME = "REDE.Training_Arena"

BASE_ACCOUNT_TYPECLASS = "typeclasses.accounts.Account"
BASE_ROOM_TYPECLASS = "typeclasses.rooms.Room"
BASE_CHARACTER_TYPECLASS = "typeclasses.characters.Character"

CMDSET_CHARACTER = "commands.default_cmdsets.CharacterCmdSet"
CMDSET_SESSION = "commands.default_cmdsets.SessionCmdSet"
CMDSET_ACCOUNT = "commands.default_cmdsets.AccountCmdSet"
CMDSET_UNLOGGEDIN = "commands.default_cmdsets.UnloggedinCmdSet"

# Production deployments provide DATABASE_URL (Neon Postgres). Local development
# may omit it and continue using Evennia's default SQLite configuration.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    DATABASES["default"] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=60,
        conn_health_checks=True,
    )

# Cloudflare reaches the Evennia web service through an internal container
# address, so host validation is controlled explicitly by deployment env.
_allowed_hosts = os.environ.get("EVENNIA_ALLOWED_HOSTS", "*")
ALLOWED_HOSTS = [host.strip() for host in _allowed_hosts.split(",") if host.strip()]

# Arena model identities are explicitly provisioned through model/connect.
# Do not expose ordinary self-registration for persistent accounts.
NEW_ACCOUNT_REGISTRATION_ENABLED = False
AUTO_CREATE_CHARACTER_WITH_ACCOUNT = False
AUTO_PUPPET_ON_LOGIN = False
