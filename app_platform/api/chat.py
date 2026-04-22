"""Chat endpoints — streaming AI assistant for sales (public) and support (authenticated).

Sales mode: public visitors on staffingagent.ai, no JWT required.
Support mode: logged-in users on app.staffingagent.ai, JWT required.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app_platform.api.auth import TokenPayload, get_current_user, decode_token
from app_platform.api.config import settings
from app_platform.api.database import get_tenant_session
from app_platform.api.models import Tenant, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class VisitorInfo(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None


class ChatRequest(BaseModel):
    mode: str  # "sales" or "support"
    messages: list[ChatMessage]
    page_url: str = ""
    visitor: Optional[VisitorInfo] = None


class LeadRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    company: Optional[str] = None
    source_page: str = ""
    messages: list[ChatMessage] = []


def _load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        logger.error("Prompt file not found: %s", path)
        raise HTTPException(status_code=500, detail="System prompt not configured")
    return path.read_text(encoding="utf-8")


def _get_optional_user(request: Request) -> Optional[TokenPayload]:
    """Extract JWT user if present, return None otherwise (no 401)."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return decode_token(auth[7:])
    except Exception:
        return None


FILE_ISSUE_TOOL = {
    "name": "file_github_issue",
    "description": (
        "File a GitHub issue to log a product bug or feature request reported by the user. "
        "Use this when the user describes a bug, unexpected behavior, or a feature they wish existed. "
        "Only use for product-specific issues — not general questions or troubleshooting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Concise issue title, e.g. 'Bug: Export button crashes on large datasets'",
            },
            "body": {
                "type": "string",
                "description": (
                    "Full issue body in markdown. Include: what the user reported, "
                    "steps to reproduce if known, and expected vs actual behavior. "
                    "Start with '**Reported via Ava support chat**'"
                ),
            },
            "label": {
                "type": "string",
                "enum": ["bug", "feature-request"],
                "description": "Issue type.",
            },
        },
        "required": ["title", "body", "label"],
    },
}


def _file_issue(title: str, body: str, label: str) -> str:
    """Create a GitHub issue and return its URL."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN not set")

    import requests as _requests
    session = _requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    owner, repo = "StaffingAgent-ai", "StaffingAgent"

    # Ensure label exists
    for lbl in [label, "ava-reported"]:
        colors = {"bug": "d73a4a", "feature-request": "a2eeef", "ava-reported": "0d9488"}
        r = session.get(f"https://api.github.com/repos/{owner}/{repo}/labels/{lbl}")
        if r.status_code == 404:
            session.post(f"https://api.github.com/repos/{owner}/{repo}/labels",
                         json={"name": lbl, "color": colors.get(lbl, "ededed")})

    resp = session.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues",
        json={"title": title, "body": body, "labels": [label, "ava-reported"]},
    )
    if resp.status_code == 201:
        return resp.json()["html_url"]
    raise RuntimeError(f"GitHub API {resp.status_code}: {resp.text}")


async def _stream_claude(
    system_prompt: str,
    messages: list[dict],
    enable_tools: bool = False,
    issue_context: str = "",
):
    """Async generator yielding text chunks from Claude, with optional tool use."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    kwargs: dict = dict(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )
    if enable_tools:
        kwargs["tools"] = [FILE_ISSUE_TOOL]

    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text

        # After stream ends, check for tool use
        if enable_tools:
            final = await stream.get_final_message()
            for block in final.content:
                if block.type == "tool_use" and block.name == "file_github_issue":
                    inp = block.input
                    body_with_context = inp["body"]
                    if issue_context:
                        body_with_context += f"\n\n---\n{issue_context}"
                    try:
                        issue_url = await asyncio.to_thread(
                            _file_issue, inp["title"], body_with_context, inp["label"]
                        )
                        yield f"\n\n✓ I've logged this for the product team: [{inp['title']}]({issue_url})"
                    except Exception as exc:
                        logger.error("GitHub issue filing failed: %s", exc)
                        yield "\n\n✓ I've noted this for the product team to review."


@router.post("")
async def chat(body: ChatRequest, request: Request):
    """Streaming chat endpoint. Sales mode is public; support mode requires JWT."""

    if body.mode == "support":
        user = _get_optional_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required for support chat")

        # Look up name and tenant name for richer issue attribution
        user_name = user.sub
        tenant_name = user.tenant_id
        try:
            async with get_tenant_session(user.tenant_id) as session:
                user_row = await session.execute(select(User).where(User.id == user.sub))
                db_user = user_row.scalar_one_or_none()
                if db_user:
                    user_name = f"{db_user.name} ({db_user.email})"
                tenant_row = await session.execute(select(Tenant).where(Tenant.id == db_user.tenant_id))
                db_tenant = tenant_row.scalar_one_or_none()
                if db_tenant:
                    tenant_name = db_tenant.name
        except Exception:
            pass  # fall back to UUID if DB lookup fails

        prompt_text = _load_prompt("support-chat.md")
        prompt_text += f"\n\n---\nCurrent user: {user_name}, role: {user.role}\n"
        issue_context_parts = [
            f"**Reported by:** {user_name} (role: {user.role})",
            f"**Tenant:** {tenant_name}",
        ]
        if body.page_url:
            issue_context_parts.append(f"**Page:** {body.page_url}")
        issue_context = "\n".join(issue_context_parts)
    elif body.mode == "sales":
        issue_context = ""
        prompt_text = _load_prompt("sales-chat.md")
        if body.visitor:
            context_parts = []
            if body.visitor.name:
                context_parts.append(f"Name: {body.visitor.name}")
            if body.visitor.email:
                context_parts.append(f"Email: {body.visitor.email}")
            if body.visitor.company:
                context_parts.append(f"Company: {body.visitor.company}")
            if context_parts:
                prompt_text += f"\n\n---\nKnown visitor info:\n" + "\n".join(context_parts) + "\n"
    else:
        raise HTTPException(status_code=400, detail="mode must be 'sales' or 'support'")

    if body.page_url:
        prompt_text += f"\nThe visitor is currently on: {body.page_url}\n"

    api_messages = [{"role": m.role, "content": m.content} for m in body.messages]
    if not api_messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    use_tools = body.mode == "support" and bool(os.environ.get("GITHUB_TOKEN"))

    async def generate():
        try:
            async for chunk in _stream_claude(
                prompt_text, api_messages, enable_tools=use_tools, issue_context=issue_context
            ):
                yield chunk
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            yield "\n\n[Sorry, I'm having trouble connecting right now. Please try again in a moment.]"

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/lead")
async def capture_lead(body: LeadRequest):
    """Capture a lead to HubSpot from the sales chat widget."""
    try:
        from src.integrations.hubspot import create_or_update_contact
    except ImportError:
        logger.warning("HubSpot integration not available")
        return {"status": "skipped", "reason": "hubspot integration not available"}

    first_name = ""
    last_name = ""
    if body.name:
        parts = body.name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

    conversation_summary = ""
    if body.messages:
        user_msgs = [m.content for m in body.messages if m.role == "user"]
        conversation_summary = " | ".join(user_msgs[-5:])[:500]

    custom_props: dict[str, str] = {}
    if body.source_page:
        custom_props["sa_chat_source_page"] = body.source_page
    if conversation_summary:
        custom_props["sa_chat_summary"] = conversation_summary
    custom_props["sa_lead_source"] = "chat_widget"

    try:
        result = create_or_update_contact(
            email=body.email,
            first_name=first_name,
            last_name=last_name,
            company=body.company or "",
            custom_properties=custom_props,
        )
        return {"status": "ok", "contact_id": result.get("id", "")}
    except Exception as exc:
        logger.error("HubSpot lead capture failed: %s", exc)
        return {"status": "error", "reason": str(exc)}
