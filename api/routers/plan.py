"""Chatbot-style entry point: turn one freeform message + attachments into a
generation run.

This route is a thin orchestration layer. It does NOT re-implement any
auth/credits/validation: it builds a `GenerateRequest` and hands it to the same
`create_generation(...)` the /api/generate path uses, in-process (no self-HTTP).

The work is split into two clearly separable steps -- build the request, then
commit it -- so a future confirm-gate could stop in between (return the built
request for user confirmation before spending credits) without restructuring.
"""

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlmodel import Session

from api.database import get_session
from api.auth import get_current_user
from api.dispatch import resolve_dispatch
from api.models import (
    GenerateResponse,
    PlanRequest,
)
from api.plan_service import plan_to_request
from api.routers.generate import create_generation

router = APIRouter(prefix="/api", tags=["plan"])


@router.post("/plan", response_model=GenerateResponse)
async def plan_generation(
    plan: PlanRequest,
    background_tasks: BackgroundTasks,
    user_token: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GenerateResponse:
    uid = user_token["uid"]

    # Step 1+2: resolve + ingest sources, parse intent, merge manual choices.
    # files/links are blank in the built request (sources already ingested
    # into input_text), so the ownership/SSRF checks in create_generation are
    # no-ops -- validation and ingestion already happened above.
    # A future confirm-gate would stop here and return `request` instead.
    request = await plan_to_request(session, uid, plan)

    # Step 3: commit. Reuses all auth/credits/validation (cost calc, atomic
    # credit deduct) via the shared function.
    return create_generation(
        request=request,
        user_token=user_token,
        session=session,
        dispatch_task=resolve_dispatch(background_tasks),
    )
