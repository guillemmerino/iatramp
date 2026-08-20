"""Application services for the training-session lifecycle."""

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from iatrain.services import (
    has_athlete_access,
    organizations_available_to_coach,
    person_for_user,
)

from .models import (
    TrainingSession,
    TrainingSessionExecution,
    TrainingSessionItem,
    TrainingSessionRevision,
)


def _active_coach_for_user(user):
    person = person_for_user(user)
    if person is None:
        raise PermissionDenied("El compte ha d'estar vinculat a una persona activa.")
    try:
        coach = person.coach_profile
    except (AttributeError, ObjectDoesNotExist):
        coach = None
    if coach is None or not coach.is_active:
        raise PermissionDenied("Cal un perfil d'entrenador actiu.")
    return person, coach


def _assert_session_access(user, session):
    person, coach = _active_coach_for_user(user)
    if not getattr(user, "is_superuser", False):
        if not organizations_available_to_coach(user).filter(pk=session.organization_id).exists():
            raise PermissionDenied("No pots gestionar sessions d'aquesta organització.")
    return person, coach


def _assert_participant_edit_access(user, revision):
    for participant in revision.participant_plans.select_related("athlete_profile__person"):
        if not has_athlete_access(
            user,
            participant.athlete_profile,
            permission="can_edit_training",
            organization=revision.session.organization,
        ):
            raise PermissionDenied(
                f"No tens permís per aprovar la planificació de {participant.athlete_profile}."
            )


@transaction.atomic
def create_training_session(
    *,
    user,
    organization,
    scheduled_start,
    expected_duration_minutes,
    discipline,
    session_scope,
    gym=None,
    training_group=None,
    creation_origin=TrainingSession.CreationOrigin.MANUAL,
):
    person, coach = _active_coach_for_user(user)
    if not getattr(user, "is_superuser", False):
        if not organizations_available_to_coach(user).filter(pk=organization.pk).exists():
            raise PermissionDenied("No pots crear sessions per a aquesta organització.")
    session = TrainingSession(
        organization=organization,
        gym=gym,
        training_group=training_group,
        scheduled_start=scheduled_start,
        expected_duration_minutes=expected_duration_minutes,
        discipline=discipline,
        session_scope=session_scope,
        responsible_coach=coach,
        creation_origin=creation_origin,
        created_by=person,
    )
    session.save()
    return session


@transaction.atomic
def create_session_revision(
    *,
    user,
    session,
    title,
    general_objective,
    planned_duration_minutes,
    supersedes=None,
    change_reason="",
    creation_origin=TrainingSession.CreationOrigin.MANUAL,
):
    person, _ = _assert_session_access(user, session)
    locked_session = TrainingSession.objects.select_for_update().get(pk=session.pk)
    next_number = (
        locked_session.revisions.aggregate(value=Max("revision_number"))["value"] or 0
    ) + 1
    if supersedes is not None and supersedes.session_id != locked_session.pk:
        raise ValidationError("La versió substituïda no pertany a aquesta sessió.")
    revision = TrainingSessionRevision(
        session=locked_session,
        revision_number=next_number,
        supersedes=supersedes,
        title=title,
        general_objective=general_objective,
        planned_duration_minutes=planned_duration_minutes,
        creation_origin=creation_origin,
        change_reason=change_reason,
        created_by=person,
    )
    revision.save()
    return revision


def validate_session_revision(revision, *, require_validated_exercises=True):
    """Validate a complete planning graph before a lifecycle transition."""

    errors = []
    if not revision.participant_plans.exists():
        errors.append("Cal planificar almenys un participant.")
    if not revision.goals.filter(priority="primary").exists():
        errors.append("Cal definir almenys un objectiu principal.")

    blocks = revision.blocks.prefetch_related(
        "items__physical_prescription",
        "items__alternatives",
        "items__athlete_adjustments",
    )
    if not blocks.exists():
        errors.append("Cal definir almenys un bloc.")
    block_duration = blocks.aggregate(total=Sum("planned_duration_minutes"))["total"] or 0
    if block_duration > revision.planned_duration_minutes:
        errors.append("La suma dels blocs supera la durada planificada de la sessió.")

    for block in blocks:
        items = list(block.items.all())
        if not items:
            errors.append(f"El bloc «{block.name}» no conté cap ítem.")
        for item in items:
            try:
                prescription = item.physical_prescription
            except TrainingSessionItem.physical_prescription.RelatedObjectDoesNotExist:
                prescription = None
            if item.item_type == TrainingSessionItem.ItemType.PHYSICAL_EXERCISE:
                if prescription is None:
                    errors.append(f"L'exercici físic «{item.title}» no té prescripció.")
                    continue
                if require_validated_exercises and prescription.exercise_revision.editorial_status != "validated":
                    errors.append(f"L'exercici «{item.title}» encara no està validat editorialment.")
                if require_validated_exercises:
                    for alternative in item.alternatives.all():
                        if alternative.exercise_revision.editorial_status != "validated":
                            errors.append(
                                f"Una alternativa de «{item.title}» encara no està validada."
                            )
                    for adjustment in item.athlete_adjustments.all():
                        replacement = adjustment.replacement_exercise_revision
                        if replacement and replacement.editorial_status != "validated":
                            errors.append(
                                f"Una adaptació de «{item.title}» usa un exercici no validat."
                            )
            elif prescription is not None:
                errors.append(f"L'ítem no físic «{item.title}» no pot tenir prescripció física.")
    if errors:
        raise ValidationError(errors)
    return revision


@transaction.atomic
def propose_session_revision(*, user, revision):
    _assert_session_access(user, revision.session)
    revision = TrainingSessionRevision.objects.select_for_update().get(pk=revision.pk)
    if revision.status != revision.Status.DRAFT:
        raise ValidationError("Només es pot proposar una versió en esborrany.")
    validate_session_revision(revision, require_validated_exercises=False)
    revision.status = revision.Status.PROPOSED
    revision.save(update_fields=("status", "updated_at"))
    return revision


@transaction.atomic
def reopen_session_revision(*, user, revision):
    _assert_session_access(user, revision.session)
    revision = TrainingSessionRevision.objects.select_for_update().get(pk=revision.pk)
    if revision.status not in {revision.Status.PROPOSED, revision.Status.REJECTED}:
        raise ValidationError("Només es pot reobrir una versió proposada o rebutjada.")
    revision.status = revision.Status.DRAFT
    revision.save(update_fields=("status", "updated_at"))
    return revision


@transaction.atomic
def approve_session_revision(*, user, revision):
    person, _ = _assert_session_access(user, revision.session)
    revision = TrainingSessionRevision.objects.select_for_update().select_related("session").get(
        pk=revision.pk
    )
    if revision.status != revision.Status.PROPOSED:
        raise ValidationError("Només es pot aprovar una versió proposada.")
    if hasattr(revision.session, "execution"):
        raise ValidationError("No es pot canviar la versió aprovada d'una sessió ja executada.")
    _assert_participant_edit_access(user, revision)
    validate_session_revision(revision, require_validated_exercises=True)

    previous = (
        TrainingSessionRevision.objects.select_for_update()
        .filter(session=revision.session, status=revision.Status.APPROVED)
        .exclude(pk=revision.pk)
        .first()
    )
    if previous:
        previous.status = previous.Status.SUPERSEDED
        previous.save(update_fields=("status", "updated_at"))
    revision.status = revision.Status.APPROVED
    revision.approved_by = person
    revision.approved_at = timezone.now()
    revision.save(update_fields=("status", "approved_by", "approved_at", "updated_at"))
    return revision


@transaction.atomic
def start_session_execution(*, user, session, supervised_by=None):
    _, coach = _assert_session_access(user, session)
    session = TrainingSession.objects.select_for_update().get(pk=session.pk)
    if session.lifecycle_status != session.LifecycleStatus.SCHEDULED:
        raise ValidationError("Només es pot iniciar una sessió programada.")
    if TrainingSessionExecution.objects.filter(session=session).exists():
        raise ValidationError("Aquesta sessió ja té una execució.")
    revision = session.revisions.filter(status=TrainingSessionRevision.Status.APPROVED).first()
    if revision is None:
        raise ValidationError("Cal una versió aprovada abans d'iniciar la sessió.")
    _assert_participant_edit_access(user, revision)
    execution = TrainingSessionExecution(
        session=session,
        approved_revision=revision,
        started_at=timezone.now(),
        status=TrainingSessionExecution.Status.IN_PROGRESS,
        supervised_by=supervised_by or coach,
    )
    execution.save()
    session.lifecycle_status = session.LifecycleStatus.IN_PROGRESS
    session.save(update_fields=("lifecycle_status", "updated_at"))
    return execution


@transaction.atomic
def complete_session_execution(*, user, execution, general_notes=None, aborted=False):
    _assert_session_access(user, execution.session)
    execution = TrainingSessionExecution.objects.select_for_update().select_related("session").get(
        pk=execution.pk
    )
    if execution.status != execution.Status.IN_PROGRESS:
        raise ValidationError("Només es pot finalitzar una execució en curs.")
    execution.status = execution.Status.ABORTED if aborted else execution.Status.COMPLETED
    execution.finished_at = timezone.now()
    if general_notes is not None:
        execution.general_notes = general_notes
    execution.save(
        update_fields=("status", "finished_at", "general_notes", "updated_at")
    )
    execution.session.lifecycle_status = execution.session.LifecycleStatus.COMPLETED
    execution.session.save(update_fields=("lifecycle_status", "updated_at"))
    return execution
