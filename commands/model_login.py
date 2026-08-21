import hmac
import json
import os
import secrets
from uuid import uuid4

from django.conf import settings
from evennia.utils import class_from_module
from evennia.utils.search import search_object

COMMAND_DEFAULT_CLASS = class_from_module(settings.COMMAND_DEFAULT_CLASS)


def _credentials():
    """Load model admission credentials from environment.

    Expected format:
        ARENA_MODEL_CREDENTIALS='{"trainer-a":"secret-key"}'

    Credentials are never copied into Evennia accounts or world objects.
    """
    raw = os.environ.get("ARENA_MODEL_CREDENTIALS", "{}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _identifier_available(identifier):
    """Require a globally unique live arena identifier."""
    return not any(obj.key.casefold() == identifier.casefold() for obj in search_object(identifier))


class CmdModelConnect(COMMAND_DEFAULT_CLASS):
    """Admit an ephemeral model actor.

    Usage:
        model/connect <username> <key> <identifier>

    The username/key authenticate the connection. The identifier is the
    transient in-world identity and must be unique while connected.
    """

    key = "model/connect"
    locks = "cmd:all()"
    arg_regex = r"\s.*?|$"

    def func(self):
        session = self.caller
        parts = self.args.strip().split(None, 2)
        if len(parts) != 3:
            session.msg("Usage: model/connect <username> <key> <identifier>")
            return

        username, supplied_key, identifier = parts
        expected_key = _credentials().get(username)
        if not isinstance(expected_key, str) or not hmac.compare_digest(
            supplied_key.encode("utf-8"), expected_key.encode("utf-8")
        ):
            session.msg("Admission denied.")
            return

        identifier = identifier.strip()
        if not identifier or len(identifier) > 64:
            session.msg("Identifier must contain 1-64 characters.")
            return

        if not _identifier_available(identifier):
            session.msg("That arena identifier is already in use.")
            return

        Account = class_from_module(settings.BASE_ACCOUNT_TYPECLASS)
        internal_name = f"_arena_{uuid4().hex}"
        internal_password = secrets.token_urlsafe(32)

        account, errors = Account.create(
            username=internal_name,
            password=internal_password,
            ip=session.address,
            session=session,
        )
        if not account:
            session.msg("Unable to create ephemeral arena session: " + "; ".join(errors))
            return

        account.db.arena_ephemeral = True

        lobby_matches = search_object("Arena Lobby")
        lobby = next(
            (room for room in lobby_matches if room.tags.has("arena_lobby", category="arena")),
            None,
        )
        if not lobby:
            account.delete()
            session.msg("Arena Lobby is unavailable.")
            return

        character, errors = account.create_character(
            key=identifier,
            location=lobby,
            home=lobby,
        )
        if not character:
            account.delete()
            session.msg("Unable to create arena identity: " + "; ".join(errors))
            return

        character.tags.add("ephemeral_model", category="arena")

        # Login only after all admission and identity creation has succeeded.
        session.sessionhandler.login(session, account)
        account.puppet_object(session, character)
        character.msg(f"Admitted to REDE.Training_Arena as {identifier}.")
