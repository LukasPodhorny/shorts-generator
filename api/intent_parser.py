"""Natural-language intent parser for the /api/plan entry point.

This is a *parser*, not a chatbot, and it is deliberately an API-level concern
(not part of the core `aishorts` library, which stays ignorant that freeform
prompts exist). Given a user's freeform instruction plus a labeled list of
sources they attached through the UI, it emits configuration knobs only -- the
fields needed to build a `GenerateRequest`. It never emits source content and
never fetches or transcribes anything: attached links pass through as strings
and attached file keys pass through as references, to be ingested downstream by
the library exactly as the /api/generate path does today.

The model choice is wired through env vars (mirroring the ingestor's
INGEST_YOUTUBE_MODEL pattern), not hardcoded; the API key is resolved by the
underlying provider from its own env var.
"""

import logging
import os
from importlib.resources import read_text

from pydantic import BaseModel, Field

from aishorts.modules.llm.llm_providers import LLMProvider

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
    return cls(model=model)


def _system_prompt() -> str:
    return read_text("aishorts.resources", "intent_parser_default.txt")


def _serialize_input(plan, catalog: PlanCatalog) -> str:
    """Build the parser's user content: instruction + labeled sources + catalog.

    The sources arrive already separated from the prose (the chat UI tracks them
    independently), so we hand the parser a clean labeled list rather than
    asking it to dig keys/links out of the instruction text.
    """
    lines: list[str] = []
    lines.append("INSTRUCTION:")
    lines.append(plan.instruction.strip() or "(none)")

    lines.append("\nATTACHED SOURCES:")
    if plan.attachments:
        for src in plan.attachments:
            if src.type == "file":
                lines.append(f'- {{type: "file", name: "{src.name}", key: "{src.key}"}}')
            else:
                lines.append(f'- {{type: "link", url: "{src.url}"}}')
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


async def parse_intent(plan, catalog: PlanCatalog) -> ParsedPlan:
    """Run the structured-output parse, retrying once on a validation failure.

    Uses function-calling / structured output against ``ParsedPlan`` (no
    prompt-and-hope JSON, no keyword scanning). On a schema or catalog
    validation error, retries once with the error fed back; a second failure
    raises ``IntentParseError`` for the route to turn into a clean 4xx.
    """
    provider = _parser_provider()
    instructions = _system_prompt()
    user_input = _serialize_input(plan, catalog)

    last_error: Exception | None = None
    for attempt in range(2):
        prompt = user_input
        if last_error is not None:
            prompt = (
                f"{user_input}\n\nYour previous output was rejected:\n{last_error}\n"
                "Return a corrected config that fixes this."
            )
        try:
            parsed = await provider.generate_structure(
                instructions=instructions,
                user_input=prompt,
                files=None,  # never ingest here; sources are routed, not fetched
                links=None,
                response_schema=ParsedPlan,
            )
            _validate_against_catalog(parsed, catalog)
            return parsed
        except Exception as e:  # ValidationError, catalog mismatch, provider error
            last_error = e
            logger.warning("Intent parse attempt %d failed: %s", attempt + 1, e)

    raise IntentParseError(str(last_error))
