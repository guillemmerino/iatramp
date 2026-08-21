"""Transactional persistence adapter for validated block proposals."""

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction

from iatrain.models import (
    BlockParticipantAssignment,
    PhysicalExercisePrescription,
    SessionItemAlternative,
    SessionItemAthleteAdjustment,
    SessionParticipantPlan,
    TrainingBlock,
    TrainingSessionItem,
    TrainingSessionRevision,
)
from iatrain.services import organizations_available_to_coach, person_for_user
from iatrain_exercises.models import ExerciseRevision

from .contracts import BlockGenerationProposal, BlockParticipantProposal
from .validation import (
    referenced_exercise_revision_ids,
    validate_block_generation_proposal,
)


def _assert_adapter_access(user, revision):
    actor = person_for_user(user)
    if actor is None:
        raise PermissionDenied("El compte ha d'estar vinculat a una persona activa.")
    try:
        coach = actor.coach_profile
    except (AttributeError, ObjectDoesNotExist):
        coach = None
    if coach is None or not coach.is_active:
        raise PermissionDenied("Cal un perfil d'entrenador actiu.")
    if not getattr(user, "is_superuser", False):
        if not organizations_available_to_coach(user).filter(
            pk=revision.session.organization_id
        ).exists():
            raise PermissionDenied("No pots generar blocs per a aquesta organització.")
    return actor


@transaction.atomic
def apply_block_generation_proposal(*, user, proposal):
    """Persist one complete proposal into an existing draft session revision.

    The adapter makes no selection decisions. It validates references, locks
    the target revision and either writes the complete block graph or nothing.
    """

    if not isinstance(proposal, BlockGenerationProposal):
        raise ValidationError("La proposta no compleix el contracte BlockGenerationProposal.")
    revision = (
        TrainingSessionRevision.objects.select_for_update()
        .select_related("session")
        .get(pk=proposal.request.session_revision_id)
    )
    actor = _assert_adapter_access(user, revision)
    validate_block_generation_proposal(
        proposal,
        revision=revision,
        exercise_owner=actor,
        require_validated_exercises=False,
    )

    exercise_revisions = ExerciseRevision.objects.in_bulk(
        referenced_exercise_revision_ids(proposal)
    )
    participant_plans = SessionParticipantPlan.objects.in_bulk(
        (
            *proposal.request.participant_plan_ids,
            *proposal.request.excluded_participant_plan_ids,
        )
    )
    request = proposal.request
    block = TrainingBlock.objects.create(
        session_revision=revision,
        sequence_index=request.sequence_index,
        name=request.name,
        block_role=request.block_role,
        domain=request.domain,
        execution_mode=request.execution_mode,
        planned_duration_minutes=request.planned_duration_minutes,
        objective=request.objective.description,
        instructions=request.instructions,
        is_optional=request.is_optional,
        rounds=request.rounds,
        rest_between_rounds_seconds=request.rest_between_rounds_seconds,
    )

    participant_rows = proposal.participants
    if not participant_rows:
        participant_rows = tuple(
            BlockParticipantProposal(participant_plan_id=value, mode="shared")
            for value in request.participant_plan_ids
        ) + tuple(
            BlockParticipantProposal(participant_plan_id=value, mode="excluded")
            for value in request.excluded_participant_plan_ids
        )
    for participant in participant_rows:
        BlockParticipantAssignment.objects.create(
            block=block,
            participant_plan=participant_plans[participant.participant_plan_id],
            mode=participant.mode,
            rationale=participant.rationale,
        )

    for proposed_item in sorted(proposal.items, key=lambda item: item.sequence_index):
        item = TrainingSessionItem.objects.create(
            block=block,
            sequence_index=proposed_item.sequence_index,
            item_type=proposed_item.item_type,
            title=proposed_item.title,
            instructions=proposed_item.instructions,
            coaching_cues=proposed_item.coaching_cues,
            planned_duration_seconds=proposed_item.planned_duration_seconds,
            rest_after_seconds=proposed_item.rest_after_seconds,
            selection_rationale=proposed_item.selection_rationale,
            is_optional=proposed_item.is_optional,
        )
        if proposed_item.dose is None:
            continue
        dose = proposed_item.dose
        PhysicalExercisePrescription.objects.create(
            session_item=item,
            exercise_revision=exercise_revisions[dose.exercise_revision_id],
            dose_mode=dose.dose_mode,
            sets=dose.sets,
            repetitions=dose.repetitions,
            duration_seconds=dose.duration_seconds,
            distance=dose.distance,
            distance_unit=dose.distance_unit,
            load_value=dose.load_value,
            load_unit=dose.load_unit,
            intensity_metric=dose.intensity_metric,
            intensity_value=dose.intensity_value,
            tempo_eccentric_seconds=dose.tempo_eccentric_seconds,
            tempo_pause_seconds=dose.tempo_pause_seconds,
            tempo_concentric_seconds=dose.tempo_concentric_seconds,
            concentric_intent=dose.concentric_intent,
            rest_between_sets_seconds=dose.rest_between_sets_seconds,
            execution_notes=dose.execution_notes,
        )
        for alternative in proposed_item.alternatives:
            SessionItemAlternative.objects.create(
                session_item=item,
                exercise_revision=exercise_revisions[alternative.exercise_revision_id],
                priority=alternative.priority,
                trigger=alternative.trigger,
                rationale=alternative.rationale,
            )
        for adjustment in proposed_item.athlete_adjustments:
            SessionItemAthleteAdjustment.objects.create(
                session_item=item,
                participant_plan=participant_plans[adjustment.participant_plan_id],
                action=adjustment.action,
                replacement_exercise_revision=(
                    exercise_revisions[adjustment.replacement_exercise_revision_id]
                    if adjustment.replacement_exercise_revision_id
                    else None
                ),
                sets=adjustment.sets,
                repetitions=adjustment.repetitions,
                duration_seconds=adjustment.duration_seconds,
                load_value=adjustment.load_value,
                load_unit=adjustment.load_unit,
                intensity_metric=adjustment.intensity_metric,
                intensity_value=adjustment.intensity_value,
                rest_between_sets_seconds=adjustment.rest_between_sets_seconds,
                adaptation_notes=adjustment.adaptation_notes,
                rationale=adjustment.rationale,
            )
    return block
