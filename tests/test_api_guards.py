"""Regression tests for API-layer fixes.

These pin down runtime properties of lines that were changed while clearing
the type-checker errors in `api/`, so a future revert breaks loudly here
instead of silently on an edge path (e.g. a Stripe webhook with a bad
signature, or the /api/plan intent parser resolving its LLM provider).
"""

import os

import pytest

# Importing `api.*` runs `load_dotenv()`, which would leak the developer's real
# `.env` (R2_BUCKET, R2_PUBLIC_DOMAIN, ...) into this pytest process and change
# the behavior of unrelated, env-sensitive tests. Snapshot and restore the
# environment around the import so this module leaves no trace for siblings.
_ENV_BEFORE_API_IMPORT = dict(os.environ)
from api.routers.users import SignatureVerificationError, stripe_webhook  # noqa: E402

os.environ.clear()
os.environ.update(_ENV_BEFORE_API_IMPORT)
del _ENV_BEFORE_API_IMPORT


def test_stripe_signature_error_importable_from_users_router():
    """The webhook handler catches this; it must resolve at module load."""
    assert issubclass(SignatureVerificationError, Exception)


def test_webhook_rejects_bad_signature_with_400():
    """Invalid payload/signature must be a clean 400, never a 500."""
    from fastapi import HTTPException

    class _Body:
        async def body(self):
            return b"bad-payload"

        @property
        def headers(self):
            return {"stripe-signature": "bad-sig"}

    import stripe

    def _raise(*args, **kwargs):
        raise SignatureVerificationError("bad sig", "sig-header")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(stripe.Webhook, "construct_event", _raise)
    try:
        with pytest.raises(HTTPException) as exc_info:
            import asyncio

            asyncio.run(stripe_webhook(_Body(), session=None))  # type: ignore[arg-type]
    finally:
        monkeypatch.undo()
    assert exc_info.value.status_code == 400


def test_llm_provider_registry_returns_registered_class():
    """`LLMProvider.get` returns the concrete class (used by /api/plan)."""
    from aishorts.modules.llm.llm_providers import Gemini, LLMProvider

    assert LLMProvider.get("gemini") is Gemini
