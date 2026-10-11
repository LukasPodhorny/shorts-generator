"""Natural-language intent parser for the /api/plan entry point.

This is a *parser*, not a chatbot, and it is deliberately an API-level concern
(not part of the core `aishorts` library, which stays ignorant that freeform
prompts exist). It emits configuration knobs only -- template, avatars, amount,
enabled tags -- the fields needed to build a `GenerateRequest`. It never emits
source content.

Sources are NOT its job: by the time the parser runs, links have already been
pulled from the prose (by regex, in `source_ingest`) and ingested to Markdown
alongside any UI-attached files. The parser is handed a short preview of that
ingested material purely to judge the topic/audience and pick a fitting
template and avatars; it does not route, fetch, or attach anything. This is the
fix for the old failure mode where a link typed into the chat was dropped
because the parser was (correctly) told not to read URLs out of prose.

The model choice is wired through env vars (mirroring the ingestor's
INGEST_YOUTUBE_MODEL pattern), not hardcoded; the API key is resolved by the
underlying provider from its own env var.
"""

import logging
import os
from importlib.resources import read_text

from pydantic import BaseModel, Field

from aishorts.modules.llm.llm_providers import LLMProvider
from api.models import PlanRequest

logger = logging.getLogger("ShortsGenerator.IntentParser")

# Same pattern as the ingestor's env-driven model selection: an env override
# with a sensible default. Structured extraction, not creative work, so this
# uses the cheap/fast Gemini model; the strong model is reserved for scripts.
DEFAULT_PARSER_PROVIDER = "gemini"
DEFAULT_PARSER_MODEL = "gemini-3.1-flash-lite"


class IntentParseError(Exception):
    """Raised when the parser cannot produce a valid config after a retry."""


class ParsedPlan(BaseModel):
    """The parser's structured output: config knobs only, never source content.

    Manual choices the user made in the UI are merged in afterwards and always
    win; the parser fills these for whatever the user left unspecified.
    """

    template_name: str = Field(
        description="The single best-fitting template name chosen from the catalog."
    )
    avatar_names: list[str] = Field(
        description="1-2 avatar names chosen from the catalog.",
        min_length=1,
        max_length=4,
    )
    amount: int = Field(
        default=1,
        ge=1,
        le=7,
        description="How many reels to generate.",
    )
    enabled_tags: list[str] | None = Field(
        default=None,
        description=(
            "Optional asset tags to enable on the chosen template. Leave null to "
            "use the template's own defaults."
        ),
    )


class PlanCatalog(BaseModel):
    """The choices the parser is allowed to pick from, loaded from the DB."""

    # template name -> the asset-type tag values that template offers
    templates: dict[str, list[str]]
    # avatar name -> short instruction snippet (helps the model pick a fit)
    avatars: dict[str, str]


def _parser_provider() -> LLMProvider:
    provider = os.getenv("INTENT_PARSER_PROVIDER", DEFAULT_PARSER_PROVIDER)
    model = os.getenv("INTENT_PARSER_MODEL", DEFAULT_PARSER_MODEL)
    cls = LLMProvider.get(provider)
    # Provider resolves its own API key from the environment; nothing hardcoded.
    # (pyright: ignore -- the registry only holds concrete providers; the
    # abstract base never sets provider_name so it can never come back here.)
    return cls(model=model)  # pyright: ignore[reportAbstractUsage]


def _system_prompt() -> str:
    return read_text("aishorts.resources", "intent_parser_default.txt")


def _serialize_input(
    plan: PlanRequest, catalog: PlanCatalog, source_preview: str | None
) -> str:
    """Build the parser's user content: instruction + source preview + catalog.

    Sources are already fetched and converted upstream; we pass only a truncated
    preview of the resulting Markdown so the parser can judge topic/audience.
    The parser neither routes nor attaches sources, so there is no source list.
    """
    lines: list[str] = []
    lines.append("INSTRUCTION:")
    lines.append(plan.instruction.strip() or "(none)")

    lines.append(
        "\nSOURCE MATERIAL (preview, already ingested upstream; may be truncated):"
    )
    preview = (source_preview or "").strip()
    if preview:
        limit = 4000
        lines.append(preview[:limit] + ("..." if len(preview) > limit else ""))
    else:
        lines.append("(none)")

    lines.append("\nAVAILABLE TEMPLATES (name -> toggleable tags):")
    for name, tags in catalog.templates.items():
        tag_str = ", ".join(tags) if tags else "no toggleable tags"
        lines.append(f"- {name}: {tag_str}")

    lines.append("\nAVAILABLE AVATARS (name -> persona):")
    for name, instructions in catalog.avatars.items():
        snippet = (instructions or "").strip().replace("\n", " ")
        if len(snippet) > 200:
            snippet = snippet[:200] + "..."
        lines.append(f"- {name}: {snippet}")

    # Tell the parser what the user already chose so it does not fight it. The
    # route still enforces "manual wins" on the merge, but echoing avoids waste.
    manual: list[str] = []
    if plan.template_name:
        manual.append(f"template_name: {plan.template_name}")
    if plan.avatar_names:
        manual.append(f"avatar_names: {plan.avatar_names}")
    if plan.amount is not None:
        manual.append(f"amount: {plan.amount}")
    if plan.enabled_tags is not None:
        manual.append(f"enabled_tags: {plan.enabled_tags}")
    lines.append("\nMANUAL CHOICES (already set by the user, keep these):")
    lines.append("\n".join(f"- {m}" for m in manual) if manual else "(none)")

    return "\n".join(lines)


def _validate_against_catalog(parsed: ParsedPlan, catalog: PlanCatalog) -> None:
    """Ensure the parser only chose names/tags that actually exist."""
    if parsed.template_name not in catalog.templates:
        raise ValueError(
            f"template_name '{parsed.template_name}' is not in the catalog. "
            f"Choose one of: {sorted(catalog.templates)}"
        )
    unknown_avatars = [a for a in parsed.avatar_names if a not in catalog.avatars]
    if unknown_avatars:
        raise ValueError(
            f"avatar_names {unknown_avatars} are not in the catalog. "
            f"Choose from: {sorted(catalog.avatars)}"
        )
    if parsed.enabled_tags:
        allowed = set(catalog.templates[parsed.template_name])
        unknown_tags = [t for t in parsed.enabled_tags if t not in allowed]
        if unknown_tags:
            raise ValueError(
                f"enabled_tags {unknown_tags} are not offered by template "
                f"'{parsed.template_name}'. Allowed: {sorted(allowed)}"
            )


async def parse_intent(
    plan: PlanRequest, catalog: PlanCatalog, source_preview: str | None = None
) -> ParsedPlan:
    """Run the structured-output parse, retrying once on a validation failure.

    Uses function-calling / structured output against ``ParsedPlan`` (no
    prompt-and-hope JSON, no keyword scanning). ``source_preview`` is a
    truncated slice of the already-ingested source Markdown, used only to inform
    template/avatar/tag choice. On a schema or catalog validation error, retries
    once with the error fed back; a second failure raises ``IntentParseError``
    for the route to turn into a clean 4xx.
    """
    provider = _parser_provider()
    instructions = _system_prompt()
    user_input = _serialize_input(plan, catalog, source_preview)

    last_error: Exception | None = None
    for attempt in range(2):
        prompt = user_input
        if last_error is not None:
            prompt = (
                f"{user_input}\n\nYour previous output was rejected:\n{last_error}\n"
                "Return a corrected config that fixes this."
            )
        try:
            raw = await provider.generate_structure(
                instructions=instructions,
                user_input=prompt,
                files=None,  # parser sees text only; sources ingested upstream
                links=None,
                response_schema=ParsedPlan,
            )
            # Normalize the provider's BaseModel to our schema (a no-op when
            # the provider honored response_schema, which it must for the
            # catalog check below to be meaningful).
            parsed = ParsedPlan.model_validate(raw)
            _validate_against_catalog(parsed, catalog)
            return parsed
        except Exception as e:  # ValidationError, catalog mismatch, provider error
            last_error = e
            logger.warning("Intent parse attempt %d failed: %s", attempt + 1, e)

    raise IntentParseError(str(last_error))
