"""Fail-closed Telegram operator resolution for Release 5A state writes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class TelegramOperatorMode(StrEnum):
    SEPARATE_ROLES = "SEPARATE_ROLES"
    SINGLE_SHARED_OPERATOR = "SINGLE_SHARED_OPERATOR"


class TelegramRole(StrEnum):
    ADULT_OWNER = "ADULT_OWNER"
    ARTEM = "ARTEM"
    VADIM = "VADIM"
    SHARED_OPERATOR = "SHARED_OPERATOR"
    READ_ONLY_MEMBER = "READ_ONLY_MEMBER"


SEPARATE_ROLE_IDENTITY_ASSURANCE = "CONFIGURED_ROLE_ID"
SHARED_IDENTITY_ASSURANCE = "SHARED_ACCOUNT_SELF_ATTESTED"
OWNER_CONFIRMATION_PHRASE = "OWNER_CONFIRMS"
OWNER_ATTESTATION_VERSION = "OWNER_CONFIRMS_V1"
FACT_SOURCE_ATTESTATION_VERSION = "FACT_SOURCE_V1"

ROLE_SETTING = {
    TelegramRole.ADULT_OWNER: "TELEGRAM_ADULT_OWNER_USER_ID",
    TelegramRole.ARTEM: "TELEGRAM_ARTEM_USER_ID",
    TelegramRole.VADIM: "TELEGRAM_VADIM_USER_ID",
}


class TelegramAuthorizationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TelegramActor:
    role: TelegramRole
    user_id: int
    username: str = ""
    operator_mode: TelegramOperatorMode = TelegramOperatorMode.SEPARATE_ROLES
    identity_assurance: str = SEPARATE_ROLE_IDENTITY_ASSURANCE
    claimed_actor_role: str = ""
    claimed_at: datetime | None = None
    attestation_version: str = ""

    @property
    def transition_actor(self) -> str:
        return {
            TelegramRole.ADULT_OWNER: "adult_owner",
            TelegramRole.ARTEM: "Artem",
            TelegramRole.VADIM: "Vadim",
            TelegramRole.SHARED_OPERATOR: "shared_operator",
            TelegramRole.READ_ONLY_MEMBER: "read_only_member",
        }[self.role]


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def configured_operator_mode(settings: Any) -> TelegramOperatorMode:
    raw = getattr(settings, "TELEGRAM_OPERATOR_MODE", None)
    if raw is None or str(raw).strip() == "":
        # Backward-compatible default for deployments that predate this hotfix.
        return TelegramOperatorMode.SEPARATE_ROLES
    try:
        return TelegramOperatorMode(str(raw).strip())
    except ValueError as exc:
        raise TelegramAuthorizationError("Unknown TELEGRAM_OPERATOR_MODE") from exc


def validate_operator_configuration(settings: Any) -> TelegramOperatorMode:
    """Validate the mutually-exclusive operator configuration without exposing IDs."""

    mode = configured_operator_mode(settings)
    shared_value = getattr(settings, "TELEGRAM_SHARED_OPERATOR_USER_ID", None)
    legacy_values = [getattr(settings, name, None) for name in ROLE_SETTING.values()]
    if mode is TelegramOperatorMode.SINGLE_SHARED_OPERATOR:
        if not _positive_int(shared_value):
            raise TelegramAuthorizationError(
                "Missing or invalid TELEGRAM_SHARED_OPERATOR_USER_ID"
            )
        if any(value is not None and str(value).strip() != "" for value in legacy_values):
            raise TelegramAuthorizationError(
                "Conflicting shared and separate Telegram operator settings"
            )
    elif shared_value is not None and str(shared_value).strip() != "":
        raise TelegramAuthorizationError(
            "Conflicting shared and separate Telegram operator settings"
        )
    else:
        provided = {
            role: getattr(settings, name, None)
            for role, name in ROLE_SETTING.items()
            if getattr(settings, name, None) is not None
            and str(getattr(settings, name, None)).strip() != ""
        }
        invalid = [ROLE_SETTING[role] for role, value in provided.items() if not _positive_int(value)]
        if invalid:
            raise TelegramAuthorizationError(
                "Invalid Telegram role setting: " + ", ".join(invalid)
            )
        duplicated_roles = [
            role
            for role, value in provided.items()
            if sum(candidate == value for candidate in provided.values()) > 1
        ]
        if duplicated_roles:
            raise TelegramAuthorizationError(
                "Conflicting Telegram role settings: "
                + ", ".join(ROLE_SETTING[role] for role in duplicated_roles)
            )
    return mode


def configured_role_ids(settings: Any) -> dict[TelegramRole, int]:
    result: dict[TelegramRole, int] = {}
    for role, setting_name in ROLE_SETTING.items():
        value = getattr(settings, setting_name, None)
        if _positive_int(value):
            result[role] = value
    return result


def resolve_telegram_actor(
    user_id: int,
    username: str,
    settings: Any,
) -> TelegramActor:
    mode = validate_operator_configuration(settings)
    if mode is TelegramOperatorMode.SINGLE_SHARED_OPERATOR:
        if settings.TELEGRAM_SHARED_OPERATOR_USER_ID == user_id:
            return TelegramActor(
                TelegramRole.SHARED_OPERATOR,
                user_id,
                username or "",
                operator_mode=mode,
                identity_assurance=SHARED_IDENTITY_ASSURANCE,
            )
        return TelegramActor(
            TelegramRole.READ_ONLY_MEMBER,
            user_id,
            username or "",
            operator_mode=mode,
            identity_assurance="UNVERIFIED_TELEGRAM_ACCOUNT",
        )
    for role, configured_id in configured_role_ids(settings).items():
        if configured_id == user_id:
            return TelegramActor(role, user_id, username or "", operator_mode=mode)
    return TelegramActor(
        TelegramRole.READ_ONLY_MEMBER,
        user_id,
        username or "",
        operator_mode=mode,
        identity_assurance="UNVERIFIED_TELEGRAM_ACCOUNT",
    )


def authorize_telegram_actor(
    user_id: int,
    username: str,
    settings: Any,
    *,
    allowed_roles: Iterable[TelegramRole],
    required_settings: Iterable[str],
    claimed_role: TelegramRole | None = None,
    attestation_version: str = "",
    allow_shared_operator: bool = False,
    claimed_at: datetime | None = None,
) -> TelegramActor:
    allowed = tuple(dict.fromkeys(allowed_roles))
    mode = validate_operator_configuration(settings)
    if mode is TelegramOperatorMode.SINGLE_SHARED_OPERATOR:
        actual = resolve_telegram_actor(user_id, username, settings)
        if actual.role is not TelegramRole.SHARED_OPERATOR:
            raise TelegramAuthorizationError(
                "Telegram account is not allowed for this command"
            )
        if claimed_role is not None:
            if claimed_role not in allowed or claimed_role not in {
                TelegramRole.ADULT_OWNER,
                TelegramRole.ARTEM,
                TelegramRole.VADIM,
            }:
                raise TelegramAuthorizationError(
                    "Self-attested action role is not allowed for this command"
                )
            return TelegramActor(
                claimed_role,
                user_id,
                username or "",
                operator_mode=mode,
                identity_assurance=SHARED_IDENTITY_ASSURANCE,
                claimed_actor_role=claimed_role.value,
                claimed_at=claimed_at or datetime.now(timezone.utc),
                attestation_version=attestation_version,
            )
        if allow_shared_operator:
            return actual
        raise TelegramAuthorizationError(
            "Shared operator must explicitly attest the action role"
        )

    missing = [
        name
        for name in required_settings
        if not _positive_int(getattr(settings, name, None))
    ]
    if missing:
        raise TelegramAuthorizationError(
            "Missing required setting: " + ", ".join(missing)
        )
    configured = configured_role_ids(settings)
    configured_allowed = [role for role in allowed if role in configured]
    if not configured_allowed:
        names = [ROLE_SETTING[role] for role in allowed if role in ROLE_SETTING]
        if names:
            raise TelegramAuthorizationError(
                "Missing required setting: " + " or ".join(names)
            )
    matching_roles = [
        role for role, configured_id in configured.items() if configured_id == user_id
    ]
    if len(matching_roles) > 1:
        conflicting = ", ".join(ROLE_SETTING[role] for role in matching_roles)
        raise TelegramAuthorizationError(
            "Conflicting Telegram role settings: " + conflicting
        )
    actor = resolve_telegram_actor(user_id, username, settings)
    if actor.role not in set(allowed):
        raise TelegramAuthorizationError(
            f"Telegram role {actor.role.value} is not allowed for this command"
        )
    if claimed_role is not None and actor.role is not claimed_role:
        raise TelegramAuthorizationError(
            "Claimed action role does not match the configured Telegram role"
        )
    if claimed_role is not None:
        return TelegramActor(
            actor.role,
            actor.user_id,
            actor.username,
            operator_mode=actor.operator_mode,
            identity_assurance=actor.identity_assurance,
            claimed_actor_role=claimed_role.value,
            claimed_at=claimed_at or datetime.now(timezone.utc),
            attestation_version=attestation_version,
        )
    return actor


def format_whoami(actor: TelegramActor) -> str:
    if actor.operator_mode is TelegramOperatorMode.SINGLE_SHARED_OPERATOR:
        account = (
            "configured shared operator"
            if actor.role is TelegramRole.SHARED_OPERATOR
            else "read-only / not configured"
        )
        assurance = (
            "SELF-ATTESTED ACTION ROLE"
            if actor.role is TelegramRole.SHARED_OPERATOR
            else "UNVERIFIED"
        )
        return (
            "<b>Telegram identity</b>\n"
            "Operator mode: <b>SINGLE_SHARED_OPERATOR</b>\n"
            f"Telegram account: <b>{account}</b>\n"
            f"Identity assurance: <b>{assurance}</b>"
        )
    return (
        "<b>Telegram identity</b>\n"
        "Operator mode: <b>SEPARATE_ROLES</b>\n"
        f"Configured role: <b>{actor.role.value}</b>\n"
        f"Telegram account: <code>{masked_user_id(actor.user_id)}</code>"
    )


def masked_user_id(user_id: int | None) -> str:
    value = str(user_id or "")
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]
