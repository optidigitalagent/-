"""Generate a truthful proposal/reply from the complete persisted event context."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Write one copy-paste-ready proposal or private-message reply for Antonov Digital.

Rules:
- Use the requested client language exactly: uk, ru, en or pl.
- Show direct understanding of the complete source specification/context.
- Give a short concrete implementation approach.
- Mention only the supplied approved evidence; never invent clients, results,
  metrics, reviews, employees, years or skills.
- Include the supplied project/milestone price and realistic timeline when they
  are available; do not invent a fixed hourly rate or reject a low budget.
- Polish communication is written with AI assistance; do not claim oral fluency.
- Keep it concise and confident, with one low-friction next step.
- Do not say that the message was sent and do not perform any platform action.
- Output only the proposal/reply text.
"""


async def generate_reply(
    title: str,
    description: str,
    platform: str,
    budget: str,
    url: str,
    client: "Any | None" = None,
    model: str = "gpt-4o-mini",
    *,
    language: str = "uk",
    client_context: str = "",
    selected_evidence: str = "",
    recommended_price: str = "",
    recommended_timeline: str = "",
    existing_proposal: str = "",
    rewrite: bool = False,
) -> str:
    """Return the stored proposal first; rewrite only on explicit request."""

    if existing_proposal.strip() and not rewrite:
        return existing_proposal.strip()

    if client is None:
        from openai import AsyncOpenAI
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import settings

        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    user_content = (
        f"Client language: {language}\n"
        f"Event/project: {title}\n"
        f"Platform: {platform}\n"
        f"Budget from source: {budget or '(not specified)'}\n"
        f"Recommended price: {recommended_price or '(not available)'}\n"
        f"Recommended timeline: {recommended_timeline or '(not available)'}\n"
        f"Approved matching evidence: {selected_evidence or '(none selected)'}\n"
        f"Available client context: {client_context or '(not available)'}\n"
        f"Complete persisted specification/message:\n{description or '(not available)'}\n"
        f"Source link: {url or '(not available)'}"
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content[:24000]},
            ],
            temperature=0.45 if rewrite else 0.3,
            max_tokens=700,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("generate_reply failed for: %s", title)
        return ""
