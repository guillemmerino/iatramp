"""Application services for generating, refining and applying block proposals."""

from django.core.exceptions import ValidationError
from django.db import transaction

from iatrain.models import BlockGenerationRun
from iatrain.services import person_for_user

from .adapter import apply_block_generation_proposal
from .context import build_block_engine_context
from .eligibility import analyze_participant_eligibility, request_after_eligibility
from .generation import ENGINE_VERSION, generate_block_proposal
from .openai import (
    PROMPT_VERSION,
    InterpretationNeedsClarification,
    interpret_block_prompt,
)
from .serialization import contract_to_payload, proposal_from_payload
from .serialization import request_from_payload


def _advance_generation_run(*, run, context, request, coach_decisions=None):
    decisions = dict(coach_decisions or {})
    review = analyze_participant_eligibility(context=context, decisions=decisions)
    run.coach_decisions = decisions
    run.decision_payload = review.payload()
    if review.needs_decision:
        run.status = BlockGenerationRun.Status.AWAITING_DECISION
        run.error_code = ""
        run.error_message = ""
        run.save()
        return run
    if not review.active_participant_plan_ids:
        raise ValidationError(
            "No queda cap gimnasta activa per generar aquest bloc físic."
        )
    final_request = request_after_eligibility(request, review)
    proposal = generate_block_proposal(context=context, request=final_request)
    run.request_payload = contract_to_payload(final_request)
    run.proposal_payload = contract_to_payload(proposal)
    run.status = BlockGenerationRun.Status.PROPOSED
    run.error_code = ""
    run.error_message = ""
    run.save()
    return run


def generate_block_run(
    *, user, revision, prompt, duration_minutes, block_role, parent_run=None, refinement=""
):
    actor = person_for_user(user)
    if actor is None:
        raise ValidationError("El compte necessita una persona activa.")
    run = BlockGenerationRun.objects.create(
        session_revision=revision,
        created_by=actor,
        parent_run=parent_run,
        prompt=prompt,
        refinement_instruction=refinement,
        prompt_version=PROMPT_VERSION,
        engine_version=ENGINE_VERSION,
        contract_version="2.0",
        request_payload={
            "planned_duration_minutes": duration_minutes,
            "block_role": block_role,
        },
    )
    try:
        context = build_block_engine_context(user=user, revision=revision)
        interpreted = interpret_block_prompt(
            context=context,
            prompt=prompt,
            duration_minutes=duration_minutes,
            block_role=block_role,
            previous_payload=(parent_run.interpretation_payload if parent_run else None),
            refinement=refinement,
        )
        run.interpretation_payload = interpreted.payload
        run.request_payload = contract_to_payload(interpreted.request)
        run.source_references = list(interpreted.source_references)
        run.model_name = interpreted.model_name
        return _advance_generation_run(
            run=run,
            context=context,
            request=interpreted.request,
            coach_decisions=(parent_run.coach_decisions if parent_run else {}),
        )
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
        run.save()
        return run
    except Exception as error:
        # Persist a concise operational error without storing API credentials or internals.
        run.status = BlockGenerationRun.Status.FAILED
        run.error_code = getattr(error, "code", "generation_failed")
        run.error_message = str(error)[:1000]
        run.save()
        try:
            error.run = run
        except (AttributeError, TypeError):
            pass
        raise


@transaction.atomic
def resume_generation_run(*, user, run, decisions=None):
    actor = person_for_user(user)
    if actor is None:
        raise ValidationError("El compte necessita una persona activa.")
    locked = BlockGenerationRun.objects.select_for_update().select_related(
        "session_revision__session"
    ).get(pk=run.pk)
    if locked.status != BlockGenerationRun.Status.AWAITING_DECISION:
        raise ValidationError("Aquesta generació no està esperant cap decisió.")
    if locked.decision_payload.get("kind") != "participant_eligibility":
        raise ValidationError("Aquest aclariment s'ha de respondre reformulant la petició.")
    allowed = {
        str(issue["participant_plan_id"]): {
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
    context = build_block_engine_context(user=user, revision=locked.session_revision)
    request = request_from_payload(locked.request_payload)
    try:
        return _advance_generation_run(
            run=locked,
            context=context,
            request=request,
            coach_decisions=merged,
        )
    except Exception as error:
        locked.status = BlockGenerationRun.Status.FAILED
        locked.error_code = getattr(error, "code", "generation_failed")
        locked.error_message = str(error)[:1000]
        locked.save()
        try:
            error.run = locked
        except (AttributeError, TypeError):
            pass
        raise


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
