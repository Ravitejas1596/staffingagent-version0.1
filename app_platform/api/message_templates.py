"""Per-tenant message template rendering for agent outbound SMS / email.

Lookup precedence (highest to lowest):

    1. Active row for (tenant_id=X, template_key, language)
    2. Active row for (tenant_id IS NULL, template_key, language) — platform default
    3. TemplateNotFoundError

Variables are whitelisted at render time. Referencing an unknown variable
raises ``TemplateVariableError`` rather than silently emitting an empty
string, because an empty ``{{ bte_link }}`` in a real SMS would send an
employee to a 404.

The whitelist intentionally leaves candidate phone / email OUT of the
variable set — those belong on the transport layer (Twilio ``to`` field,
SES ``to`` header), not in message bodies, and including them in templates
would create an easy path for a tenant admin to accidentally exfiltrate PII
into platform logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

from jinja2 import StrictUndefined
from jinja2.exceptions import UndefinedError
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app_platform.api.models import MessageTemplate


class TemplateError(Exception):
    """Base class for template errors."""


class TemplateNotFoundError(TemplateError):
    """No active template row matched the (key, tenant, language) lookup."""


class TemplateVariableError(TemplateError):
    """Template body references a variable not in the allowed whitelist, or
    the caller passed a value that failed validation."""


ALLOWED_VARIABLES: frozenset[str] = frozenset(
    {
        "employee_first_name",
        "week_ending_date",
        "bte_link",
        "recruiter_name",
        "company_short_name",
        "pay_period_start",
        "pay_period_end",
    }
)


ALLOWED_CHANNELS: frozenset[str] = frozenset({"sms", "email_subject", "email_body"})


@dataclass(frozen=True)
class RenderedMessage:
    """A rendered template ready for transport."""

    template_key: str
    channel: str
    language: str
    body: str
    subject: str | None
    source: str  # "tenant_override" | "platform_default"


def _build_env() -> SandboxedEnvironment:
    """Sandboxed Jinja2 environment with StrictUndefined.

    Sandbox blocks attribute traversal to stop a template from reaching into
    Python internals. StrictUndefined converts missing variables into
    exceptions at render time instead of empty strings.
    """
    env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    # Narrow the global namespace; we don't need any of Jinja's stdlib helpers
    # for flat variable substitution.
    env.globals = {}
    return env


_ENV: SandboxedEnvironment = _build_env()


def _validate_variables(variables: dict[str, Any]) -> None:
    unknown = set(variables.keys()) - ALLOWED_VARIABLES
    if unknown:
        raise TemplateVariableError(
            f"Unknown template variables: {sorted(unknown)}. "
            f"Allowed: {sorted(ALLOWED_VARIABLES)}"
        )
    for key, value in variables.items():
        if value is None:
            raise TemplateVariableError(f"Variable {key!r} is None.")
        if isinstance(value, str) and not value.strip():
            raise TemplateVariableError(f"Variable {key!r} is empty.")


async def _fetch_template(
    session: AsyncSession,
    *,
    template_key: str,
    tenant_id: UUID | None,
    language: str,
) -> MessageTemplate | None:
    """Return the highest-precedence active template matching the lookup.

    Tenant-scoped rows beat platform defaults, so we fetch both candidate
    rows in one query and pick the tenant row if present.
    """
    candidate_tenants: list[UUID | None] = [None]
    if tenant_id is not None:
        candidate_tenants.append(tenant_id)

    stmt = (
        select(MessageTemplate)
        .where(
            and_(
                MessageTemplate.template_key == template_key,
                MessageTemplate.language == language,
                MessageTemplate.active.is_(True),
                or_(
                    *[
                        (MessageTemplate.tenant_id.is_(None))
                        if t is None
                        else (MessageTemplate.tenant_id == t)
                        for t in candidate_tenants
                    ]
                ),
            )
        )
    )
    rows: Iterable[MessageTemplate] = (await session.execute(stmt)).scalars().all()
    tenant_row = next(
        (r for r in rows if tenant_id is not None and r.tenant_id == tenant_id),
        None,
    )
    if tenant_row is not None:
        return tenant_row
    return next((r for r in rows if r.tenant_id is None), None)


async def render(
    session: AsyncSession,
    *,
    template_key: str,
    tenant_id: UUID | None,
    variables: dict[str, Any],
    language: str = "en",
) -> RenderedMessage:
    """Render a template for a tenant, falling back to the platform default."""
    _validate_variables(variables)

    row = await _fetch_template(
        session,
        template_key=template_key,
        tenant_id=tenant_id,
        language=language,
    )
    if row is None:
        raise TemplateNotFoundError(
            f"No active template for key={template_key!r} language={language!r} "
            f"tenant_id={tenant_id}. Seed a platform default or create a "
            f"tenant override."
        )

    try:
        body = _ENV.from_string(row.body).render(**variables)
        subject = (
            _ENV.from_string(row.subject).render(**variables)
            if row.subject is not None
            else None
        )
    except UndefinedError as exc:
        raise TemplateVariableError(
            f"Template {template_key!r} references an undefined variable: {exc}"
        ) from exc

    source = "tenant_override" if row.tenant_id is not None else "platform_default"
    return RenderedMessage(
        template_key=template_key,
        channel=row.channel,
        language=row.language,
        body=body,
        subject=subject,
        source=source,
    )
