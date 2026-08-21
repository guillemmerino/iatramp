"""Application services for agentic generation, refinement and application."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from iatrain.models import BlockGenerationRun
from iatrain.services import person_for_user

from .adapter import apply_block_generation_proposal
from .agent import (
    AGENT_ENGINE_VERSION,
    AGENT_PROMPT_VERSION,
    AgentNeedsCoachDecision,
    plan_block_with_agent,
)
from .context import build_block_engine_context
from .eligibility import analyze_participant_eligibility
from .openai import InterpretationNeedsClarification
from .serialization import contract_to_payload, proposal_from_payload


def _progress(run, event):
    payload = {
        "stage": event.get("stage", "processing"),
        "message": event.get("message", "Preparant la generació…"),
        "round": int(event.get("round", 0) or 0),
        "tool_calls": int(event.get("tool_calls", 0) or 0),
        "updated_at": timezone.now().isoformat(),
    }
    if event.get("validation_errors"):
        payload["validation_errors"] = list(event["validation_errors"][:3])
    updates = {"progress_payload": payload, "updated_at": timezone.now()}
    if "trace" in event:
        updates["agent_trace"] = list(event["trace"])
    if "response_ids" in event:
        updates["response_ids"] = list(event["response_ids"])
    if "usage_payload" in event:
        updates["usage_payload"] = dict(event["usage_payload"])
    BlockGenerationRun.objects.filter(pk=run.pk).update(**updates)
    run.progress_payload = payload
    if "trace" in event:
        run.agent_trace = list(event["trace"])
    if "response_ids" in event:
        run.response_ids = list(event["response_ids"])
    if "usage_payload" in event:
        run.usage_payload = dict(event["usage_payload"])


def _complete_agent_run(
    *, run, context, duration_minutes, block_role, coach_decisions=None,
    previous_proposal=None
):
    decisions = dict(coach_decisions or {})
    review = analyze_participant_eligibility(context=context, decisions=decisions)
    run.coach_decisions = decisions
    run.decision_payload = review.payload()
    if review.needs_decision:
        run.status = BlockGenerationRun.Status.AWAITING_DECISION
        run.error_code = ""
        run.error_message = ""
        run.progress_payload = {
            "stage": "awaiting_decision",
            "message": "Cal una decisió de l’entrenador abans de continuar.",
            "updated_at": timezone.now().isoformat(),
        }
        run.save()
        return run
    if not review.active_participant_plan_ids:
        raise ValidationError(
            "No queda cap gimnasta activa per generar aquest bloc físic."
        )
    result = plan_block_with_agent(
        context=context,
        prompt=run.prompt,
        duration_minutes=duration_minutes,
        block_role=block_role,
        active_participant_ids=review.active_participant_plan_ids,
        excluded_participant_ids=review.excluded_participant_plan_ids,
        previous_proposal=previous_proposal,
        refinement=run.refinement_instruction,
        coach_decisions=decisions,
        progress_callback=lambda event: _progress(run, event),
    )
    run.interpretation_payload = result.interpretation_payload
    run.request_payload = contract_to_payload(result.proposal.request)
    run.proposal_payload = contract_to_payload(result.proposal)
    run.source_references = []
    run.model_name = result.model_name
    run.agent_trace = list(result.tool_trace)
    run.response_ids = list(result.response_ids)
    run.usage_payload = result.usage_payload
    run.validation_payload = result.validation_payload
    run.progress_payload = {
        "stage": "completed",
        "message": "Proposta preparada i validada.",
        "round": len(result.response_ids),
        "tool_calls": len(result.tool_trace),
        "updated_at": timezone.now().isoformat(),
    }
    run.status = BlockGenerationRun.Status.PROPOSED
    run.error_code = ""
    run.error_message = ""
    run.save()
    return run


def create_block_generation_run(
    *, user, revision, prompt, duration_minutes, block_role, parent_run=None,
    refinement=""
):
    actor = person_for_user(user)
    if actor is None:
        raise ValidationError("El compte necessita una persona activa.")
    return BlockGenerationRun.objects.create(
        session_revision=revision,
        created_by=actor,
        parent_run=parent_run,
        prompt=prompt,
        refinement_instruction=refinement,
        prompt_version=AGENT_PROMPT_VERSION,
        engine_version=AGENT_ENGINE_VERSION,
        contract_version="3.1",
        request_payload={
            "planned_duration_minutes": duration_minutes,
            "block_role": block_role,
        },
        progress_payload={
            "stage": "queued",
            "message": "Generació enviada a la cua…",
            "round": 0,
            "tool_calls": 0,
            "updated_at": timezone.now().isoformat(),
        },
    )


def _mark_failed(run, error):
    run.status = BlockGenerationRun.Status.FAILED
    run.error_code = getattr(error, "code", "generation_failed")
    run.error_message = str(error)[:1000]
    run.agent_trace = list(getattr(error, "agent_trace", run.agent_trace or []))
    run.response_ids = list(getattr(error, "response_ids", run.response_ids or []))
    run.usage_payload = dict(getattr(error, "usage_payload", run.usage_payload or {}))
    run.validation_payload = dict(
        getattr(error, "validation_payload", run.validation_payload or {})
    )
    run.model_name = getattr(error, "model_name", run.model_name)
    run.progress_payload = {
        "stage": "failed",
        "message": "La generació no s’ha pogut completar.",
        "round": len(run.response_ids),
        "tool_calls": len(run.agent_trace),
        "updated_at": timezone.now().isoformat(),
    }
    run.save()
    try:
        error.run = run
    except (AttributeError, TypeError):
        pass


def execute_block_generation_run(*, user, run):
    """Execute an existing processing run; safe for Celery or synchronous callers."""

    with transaction.atomic():
        locked = BlockGenerationRun.objects.select_for_update().select_related(
            "session_revision__session"
        ).get(pk=run.pk)
        if locked.status != BlockGenerationRun.Status.PROCESSING:
            return locked
        if locked.progress_payload.get("worker_started_at"):
            return locked
        locked.progress_payload = {
            "stage": "starting",
            "message": "Preparant el context de la sessió…",
            "round": 0,
            "tool_calls": 0,
            "worker_started_at": timezone.now().isoformat(),
            "updated_at": timezone.now().isoformat(),
        }
        locked.save(update_fields=("progress_payload", "updated_at"))
    run = locked
    duration_minutes = int(run.request_payload["planned_duration_minutes"])
    block_role = run.request_payload["block_role"]
    parent_run = run.parent_run
    try:
        context = build_block_engine_context(user=user, revision=run.session_revision)
        return _complete_agent_run(
            run=run,
            context=context,
            duration_minutes=duration_minutes,
            block_role=block_role,
            coach_decisions=(
                run.coach_decisions
                or (parent_run.coach_decisions if parent_run else {})
            ),
            previous_proposal=(parent_run.proposal_payload if parent_run else None),
        )
    except AgentNeedsCoachDecision as error:
        run.model_name = error.model_name
        run.agent_trace = list(error.agent_trace)
        run.response_ids = list(error.response_ids)
        run.usage_payload = dict(error.usage_payload)
        run.validation_payload = dict(error.validation_payload)
        run.status = BlockGenerationRun.Status.AWAITING_DECISION
        run.decision_payload = {
            "version": "1.1",
            "kind": "generation_blockers",
            "issues": list(error.issues),
        }
        run.error_code = error.code
        run.error_message = str(error)
        run.progress_payload = {
            "stage": "awaiting_decision",
            "message": str(error),
            "round": len(run.response_ids),
            "tool_calls": len(run.agent_trace),
            "updated_at": timezone.now().isoformat(),
        }
        run.save()
        return run
    except InterpretationNeedsClarification as error:
        run.interpretation_payload = error.payload
        run.model_name = error.model_name
        run.status = BlockGenerationRun.Status.AWAITING_DECISION
        run.decision_payload = {
            "version": "1.0",
            "kind": "intent_clarification",
            "question": error.question,
        }
        run.error_code = error.code
        run.error_message = error.question
        run.progress_payload = {
            "stage": "awaiting_decision",
            "message": "El model necessita concretar la intenció del bloc.",
            "updated_at": timezone.now().isoformat(),
        }
        run.save()
        return run
    except Exception as error:
        _mark_failed(run, error)
        raise


def generate_block_run(
    *, user, revision, prompt, duration_minutes, block_role, parent_run=None,
    refinement=""
):
    """Compatibility path used by tests and non-HTTP synchronous callers."""

    run = create_block_generation_run(
        user=user,
        revision=revision,
        prompt=prompt,
        duration_minutes=duration_minutes,
        block_role=block_role,
        parent_run=parent_run,
        refinement=refinement,
    )
    return execute_block_generation_run(user=user, run=run)


@transaction.atomic
def prepare_resume_generation_run(*, user, run, decisions=None):
    actor = person_for_user(user)
    if actor is None:
        raise ValidationError("El compte necessita una persona activa.")
    locked = BlockGenerationRun.objects.select_for_update().select_related(
        "session_revision__session"
    ).get(pk=run.pk)
    if locked.status != BlockGenerationRun.Status.AWAITING_DECISION:
        raise ValidationError("Aquesta generació no està esperant cap decisió.")
    if locked.decision_payload.get("kind") not in {
        "participant_eligibility",
        "generation_blockers",
    }:
        raise ValidationError("Aquest aclariment s'ha de respondre reformulant la petició.")
    allowed = {
        str(issue.get("decision_key", issue.get("participant_plan_id"))): {
            choice["value"] for choice in issue.get("choices", [])
        }
        for issue in locked.decision_payload.get("issues", [])
    }
    merged = dict(locked.coach_decisions or {})
    for key, value in (decisions or {}).items():
        key = str(key)
        if key not in allowed or value not in allowed[key]:
            raise ValidationError("Hi ha una decisió de participant no vàlida.")
        merged[key] = value
    locked.coach_decisions = merged
    locked.status = BlockGenerationRun.Status.PROCESSING
    locked.error_code = ""
    locked.error_message = ""
    locked.progress_payload = {
        "stage": "queued",
        "message": "Decisions rebudes; reprenent la planificació…",
        "round": 0,
        "tool_calls": 0,
        "updated_at": timezone.now().isoformat(),
    }
    locked.save()
    return locked


def resume_generation_run(*, user, run, decisions=None):
    locked = prepare_resume_generation_run(user=user, run=run, decisions=decisions)
    return execute_block_generation_run(user=user, run=locked)


@transaction.atomic
def apply_generation_run(*, user, run):
    locked = BlockGenerationRun.objects.select_for_update().select_related(
        "session_revision__session"
    ).get(pk=run.pk)
    if locked.status != BlockGenerationRun.Status.PROPOSED:
        raise ValidationError("Aquesta proposta ja no es pot aplicar.")
    proposal = proposal_from_payload(locked.proposal_payload)
    block = apply_block_generation_proposal(user=user, proposal=proposal)
    locked.applied_block = block
    locked.status = BlockGenerationRun.Status.APPLIED
    locked.save()
    return block


def discard_generation_run(*, run):
    if run.status not in {
        BlockGenerationRun.Status.PROPOSED,
        BlockGenerationRun.Status.AWAITING_DECISION,
    }:
        raise ValidationError("Aquesta proposta ja no es pot descartar.")
    run.status = BlockGenerationRun.Status.DISCARDED
    run.save()
    return run
