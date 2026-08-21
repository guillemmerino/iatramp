"""Application services for generating, refining and applying block proposals."""

from django.core.exceptions import ValidationError
from django.db import transaction

from iatrain.models import BlockGenerationRun
from iatrain.services import person_for_user

from .adapter import apply_block_generation_proposal
from .context import build_block_engine_context
from .generation import ENGINE_VERSION, generate_block_proposal
from .openai import (
    PROMPT_VERSION,
    InterpretationNeedsClarification,
    interpret_block_prompt,
)
from .serialization import contract_to_payload, proposal_from_payload


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
        proposal = generate_block_proposal(context=context, request=interpreted.request)
        run.interpretation_payload = interpreted.payload
        run.request_payload = contract_to_payload(interpreted.request)
        run.proposal_payload = contract_to_payload(proposal)
        run.source_references = list(interpreted.source_references)
        run.model_name = interpreted.model_name
        run.status = BlockGenerationRun.Status.PROPOSED
        run.error_code = ""
        run.error_message = ""
        run.save()
        return run
    except InterpretationNeedsClarification as error:
        run.interpretation_payload = error.payload
        run.status = BlockGenerationRun.Status.FAILED
        run.error_code = error.code
        run.error_message = error.question
        run.save()
        error.run = run
        raise
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
    if run.status != BlockGenerationRun.Status.PROPOSED:
        raise ValidationError("Aquesta proposta ja no es pot descartar.")
    run.status = BlockGenerationRun.Status.DISCARDED
    run.save()
    return run
