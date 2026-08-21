"""IA Train-owned identity consolidation rules."""

from django.db.models import Q

from .models import (
    AthleteCondition,
    AthleteInsight,
    AthleteMeasurement,
    AthleteObservation,
    AthleteProfile,
    AthleteSportProfile,
    BlockParticipantAssignment,
    CoachAthleteRelation,
    CoachProfile,
    ElementNotation,
    ElementRotation,
    Gym,
    KnowledgeConcept,
    KnowledgeEditorialEvent,
    KnowledgeRelation,
    TrainingContext,
    TrainingItemResult,
    TrainingSession,
    TrainingSessionExecution,
    TrainingSessionRevision,
    TrainingGroup,
    TrainingGroupMembership,
    SessionAttendance,
    SessionItemAthleteAdjustment,
    SessionParticipantPlan,
)


def _merge_coach_athlete_relations(
    *, canonical_coach, duplicate_coach, canonical_athlete, duplicate_athlete
):
    relations = (
        CoachAthleteRelation.objects.select_for_update().filter(
            Q(coach_profile=duplicate_coach) | Q(athlete_profile=duplicate_athlete)
        )
        if duplicate_coach or duplicate_athlete
        else CoachAthleteRelation.objects.none()
    )
    for source in list(relations):
        new_coach = (
            canonical_coach
            if source.coach_profile_id == getattr(duplicate_coach, "pk", None)
            else source.coach_profile
        )
        new_athlete = (
            canonical_athlete
            if source.athlete_profile_id == getattr(duplicate_athlete, "pk", None)
            else source.athlete_profile
        )
        if new_coach.person_id == new_athlete.person_id:
            source.delete()
            continue
        target = (
            CoachAthleteRelation.objects.select_for_update()
            .filter(
                coach_profile=new_coach,
                athlete_profile=new_athlete,
                organization=source.organization,
                function=source.function,
            )
            .exclude(pk=source.pk)
            .first()
        )
        if target is None:
            source.coach_profile = new_coach
            source.athlete_profile = new_athlete
            source.save(update_fields=("coach_profile", "athlete_profile", "updated_at"))
            continue
        target.can_view_profile = target.can_view_profile or source.can_view_profile
        target.can_view_training = target.can_view_training or source.can_view_training
        target.can_edit_training = target.can_edit_training or source.can_edit_training
        target.can_view_health_data = (
            target.can_view_health_data or source.can_view_health_data
        )
        target.is_active = target.is_active or source.is_active
        target.start_date = min(target.start_date, source.start_date)
        if target.end_date is None or source.end_date is None:
            target.end_date = None
        else:
            target.end_date = max(target.end_date, source.end_date)
        if source.notes and source.notes not in target.notes:
            target.notes = "\n\n".join(filter(None, (target.notes, source.notes)))
        target.save()
        source.delete()


def _merge_group_memberships(*, canonical_athlete, duplicate_athlete):
    for source in list(
        TrainingGroupMembership.objects.select_for_update().filter(
            athlete_profile=duplicate_athlete
        )
    ):
        target = None
        if source.is_active:
            target = TrainingGroupMembership.objects.select_for_update().filter(
                training_group=source.training_group,
                athlete_profile=canonical_athlete,
                is_active=True,
            ).first()
        if target is None:
            source.athlete_profile = canonical_athlete
            source.save(update_fields=("athlete_profile", "updated_at"))
            continue
        target.start_date = min(target.start_date, source.start_date)
        if target.end_date is None or source.end_date is None:
            target.end_date = None
        else:
            target.end_date = max(target.end_date, source.end_date)
        if source.notes and source.notes not in target.notes:
            target.notes = "\n\n".join(filter(None, (target.notes, source.notes)))
        target.save()
        source.delete()


def _merge_coach_owned_data(*, canonical_coach, duplicate_coach):
    if duplicate_coach is None:
        return
    Gym.objects.filter(created_by=duplicate_coach).update(created_by=canonical_coach)
    for group in TrainingGroup.objects.select_for_update().filter(
        managing_coaches=duplicate_coach
    ):
        group.managing_coaches.add(canonical_coach)
        group.managing_coaches.remove(duplicate_coach)


def _joined_notes(*values):
    result = []
    for value in values:
        value = str(value or "").strip()
        if value and value not in result:
            result.append(value)
    return "\n\n".join(result)


def _merge_training_participant_plans(*, canonical_athlete, duplicate_athlete):
    """Retarget immutable plans without losing per-athlete adjustments."""

    for source in list(
        SessionParticipantPlan.objects.select_for_update().filter(
            athlete_profile=duplicate_athlete
        )
    ):
        target = (
            SessionParticipantPlan.objects.select_for_update()
            .filter(
                session_revision=source.session_revision,
                athlete_profile=canonical_athlete,
            )
            .exclude(pk=source.pk)
            .first()
        )
        if target is None:
            SessionParticipantPlan.objects.filter(pk=source.pk).update(
                athlete_profile=canonical_athlete
            )
            continue

        for adjustment in list(
            SessionItemAthleteAdjustment.objects.select_for_update().filter(
                participant_plan=source
            )
        ):
            existing = (
                SessionItemAthleteAdjustment.objects.select_for_update()
                .filter(session_item=adjustment.session_item, participant_plan=target)
                .exclude(pk=adjustment.pk)
                .first()
            )
            if existing is None:
                SessionItemAthleteAdjustment.objects.filter(pk=adjustment.pk).update(
                    participant_plan=target
                )
                continue
            SessionItemAthleteAdjustment.objects.filter(pk=existing.pk).update(
                adaptation_notes=_joined_notes(
                    existing.adaptation_notes, adjustment.adaptation_notes
                ),
                rationale=_joined_notes(existing.rationale, adjustment.rationale),
            )
            SessionItemAthleteAdjustment.objects.filter(pk=adjustment.pk).delete()

        mode_priority = {"shared": 0, "personalized": 1, "excluded": 2}
        for assignment in list(
            BlockParticipantAssignment.objects.select_for_update().filter(
                participant_plan=source
            )
        ):
            existing = (
                BlockParticipantAssignment.objects.select_for_update()
                .filter(block=assignment.block, participant_plan=target)
                .exclude(pk=assignment.pk)
                .first()
            )
            if existing is None:
                BlockParticipantAssignment.objects.filter(pk=assignment.pk).update(
                    participant_plan=target
                )
                continue
            safest_mode = max(
                (existing.mode, assignment.mode), key=mode_priority.__getitem__
            )
            BlockParticipantAssignment.objects.filter(pk=existing.pk).update(
                mode=safest_mode,
                rationale=_joined_notes(existing.rationale, assignment.rationale),
            )
            BlockParticipantAssignment.objects.filter(pk=assignment.pk).delete()

        SessionParticipantPlan.objects.filter(pk=target.pk).update(
            individual_objective=_joined_notes(
                target.individual_objective, source.individual_objective
            ),
            planning_notes=_joined_notes(target.planning_notes, source.planning_notes),
        )
        SessionParticipantPlan.objects.filter(pk=source.pk).delete()


def _merge_training_attendance(*, canonical_athlete, duplicate_athlete):
    status_priority = {"absent": 0, "excused": 1, "partial": 2, "present": 3}
    for source in list(
        SessionAttendance.objects.select_for_update().filter(
            athlete_profile=duplicate_athlete
        )
    ):
        target = (
            SessionAttendance.objects.select_for_update()
            .filter(execution=source.execution, athlete_profile=canonical_athlete)
            .exclude(pk=source.pk)
            .first()
        )
        if target is None:
            SessionAttendance.objects.filter(pk=source.pk).update(
                athlete_profile=canonical_athlete
            )
            continue
        status = max(
            (target.status, source.status), key=lambda value: status_priority.get(value, 0)
        )
        joined_values = [value for value in (target.joined_at, source.joined_at) if value]
        left_values = [value for value in (target.left_at, source.left_at) if value]
        SessionAttendance.objects.filter(pk=target.pk).update(
            status=status,
            joined_at=min(joined_values) if joined_values else None,
            left_at=max(left_values) if left_values else None,
            notes=_joined_notes(target.notes, source.notes),
        )
        SessionAttendance.objects.filter(pk=source.pk).delete()


def _merge_training_results(*, canonical_athlete, duplicate_athlete):
    for source in list(
        TrainingItemResult.objects.select_for_update().filter(
            athlete_profile=duplicate_athlete
        )
    ):
        target = (
            TrainingItemResult.objects.select_for_update()
            .filter(
                execution=source.execution,
                session_item=source.session_item,
                athlete_profile=canonical_athlete,
            )
            .exclude(pk=source.pk)
            .first()
        )
        if target is None:
            TrainingItemResult.objects.filter(pk=source.pk).update(
                athlete_profile=canonical_athlete
            )
            continue
        TrainingItemResult.objects.filter(pk=target.pk).update(
            athlete_feedback=_joined_notes(
                target.athlete_feedback, source.athlete_feedback
            ),
            coach_feedback=_joined_notes(target.coach_feedback, source.coach_feedback),
        )
        TrainingItemResult.objects.filter(pk=source.pk).delete()


def _merge_athlete_sport_profiles(*, canonical_athlete, duplicate_athlete):
    for source in list(
        AthleteSportProfile.objects.select_for_update().filter(
            athlete_profile=duplicate_athlete
        )
    ):
        target = (
            AthleteSportProfile.objects.select_for_update()
            .filter(
                athlete_profile=canonical_athlete,
                discipline=source.discipline,
            )
            .exclude(pk=source.pk)
            .first()
        )
        if target is None:
            AthleteSportProfile.objects.filter(pk=source.pk).update(
                athlete_profile=canonical_athlete
            )
            continue
        start_dates = [
            value
            for value in (target.training_started_on, source.training_started_on)
            if value
        ]
        AthleteSportProfile.objects.filter(pk=target.pk).update(
            level_code=target.level_code or source.level_code,
            training_started_on=min(start_dates) if start_dates else None,
            preferred_laterality=(
                source.preferred_laterality
                if target.preferred_laterality == AthleteSportProfile.Laterality.UNKNOWN
                else target.preferred_laterality
            ),
            notes=_joined_notes(target.notes, source.notes),
            is_active=target.is_active or source.is_active,
        )
        AthleteSportProfile.objects.filter(pk=source.pk).delete()


def merge_iatrain_identity(*, canonical, duplicate):
    """Retarget all IA Train data before Core removes the duplicate person."""
    canonical_athlete = AthleteProfile.objects.select_for_update().filter(
        person=canonical
    ).first()
    duplicate_athlete = AthleteProfile.objects.select_for_update().filter(
        person=duplicate
    ).first()
    canonical_coach = CoachProfile.objects.select_for_update().filter(person=canonical).first()
    duplicate_coach = CoachProfile.objects.select_for_update().filter(person=duplicate).first()

    if canonical_athlete is None and duplicate_athlete is not None:
        duplicate_athlete.person = canonical
        duplicate_athlete.save(update_fields=("person", "updated_at"))
        canonical_athlete, duplicate_athlete = duplicate_athlete, None
    if canonical_coach is None and duplicate_coach is not None:
        duplicate_coach.person = canonical
        duplicate_coach.save(update_fields=("person", "updated_at"))
        canonical_coach, duplicate_coach = duplicate_coach, None

    _merge_coach_athlete_relations(
        canonical_coach=canonical_coach,
        duplicate_coach=duplicate_coach,
        canonical_athlete=canonical_athlete,
        duplicate_athlete=duplicate_athlete,
    )

    if duplicate_athlete is not None:
        _merge_group_memberships(
            canonical_athlete=canonical_athlete,
            duplicate_athlete=duplicate_athlete,
        )
        _merge_training_participant_plans(
            canonical_athlete=canonical_athlete,
            duplicate_athlete=duplicate_athlete,
        )
        _merge_training_attendance(
            canonical_athlete=canonical_athlete,
            duplicate_athlete=duplicate_athlete,
        )
        _merge_training_results(
            canonical_athlete=canonical_athlete,
            duplicate_athlete=duplicate_athlete,
        )
        _merge_athlete_sport_profiles(
            canonical_athlete=canonical_athlete,
            duplicate_athlete=duplicate_athlete,
        )
        AthleteMeasurement.objects.filter(athlete_profile=duplicate_athlete).update(
            athlete_profile=canonical_athlete
        )
        AthleteCondition.objects.filter(athlete_profile=duplicate_athlete).update(
            athlete_profile=canonical_athlete
        )
        AthleteInsight.objects.filter(athlete_profile=duplicate_athlete).update(
            athlete_profile=canonical_athlete
        )
        canonical_athlete.settings = {
            **duplicate_athlete.settings,
            **canonical_athlete.settings,
        }
        canonical_athlete.extracted_facts = [
            *duplicate_athlete.extracted_facts,
            *canonical_athlete.extracted_facts,
        ]
        canonical_athlete.is_active = (
            canonical_athlete.is_active or duplicate_athlete.is_active
        )
        canonical_athlete.save()
        duplicate_athlete.delete()

    if duplicate_coach is not None:
        _merge_coach_owned_data(
            canonical_coach=canonical_coach,
            duplicate_coach=duplicate_coach,
        )
        TrainingSession.objects.filter(responsible_coach=duplicate_coach).update(
            responsible_coach=canonical_coach
        )
        TrainingSessionExecution.objects.filter(supervised_by=duplicate_coach).update(
            supervised_by=canonical_coach
        )
        canonical_coach.settings = {
            **duplicate_coach.settings,
            **canonical_coach.settings,
        }
        canonical_coach.is_active = canonical_coach.is_active or duplicate_coach.is_active
        canonical_coach.save()
        duplicate_coach.delete()

    TrainingContext.objects.filter(responsible_coach=duplicate).update(
        responsible_coach=canonical
    )
    for training_context in TrainingContext.objects.filter(athletes=duplicate):
        training_context.athletes.add(canonical)
        training_context.athletes.remove(duplicate)

    person_authored_models = (
        KnowledgeConcept,
        KnowledgeRelation,
        ElementRotation,
        ElementNotation,
    )
    for model in person_authored_models:
        model.objects.filter(authored_by=duplicate).update(authored_by=canonical)
    for model in (KnowledgeConcept, KnowledgeRelation, ElementRotation):
        model.objects.filter(last_validated_by=duplicate).update(last_validated_by=canonical)
    KnowledgeEditorialEvent.objects.filter(decided_by=duplicate).update(decided_by=canonical)
    AthleteObservation.objects.filter(athlete=duplicate).update(athlete=canonical)
    AthleteObservation.objects.filter(authored_by=duplicate).update(authored_by=canonical)
    AthleteSportProfile.objects.filter(updated_by=duplicate).update(updated_by=canonical)
    AthleteMeasurement.objects.filter(recorded_by=duplicate).update(recorded_by=canonical)
    AthleteCondition.objects.filter(recorded_by=duplicate).update(recorded_by=canonical)
    AthleteCondition.objects.filter(confirmed_by=duplicate).update(confirmed_by=canonical)
    AthleteInsight.objects.filter(triggered_by=duplicate).update(triggered_by=canonical)
    AthleteInsight.objects.filter(confirmed_by=duplicate).update(confirmed_by=canonical)
    TrainingSession.objects.filter(created_by=duplicate).update(created_by=canonical)
    TrainingSessionRevision.objects.filter(created_by=duplicate).update(created_by=canonical)
    TrainingSessionRevision.objects.filter(approved_by=duplicate).update(approved_by=canonical)
    TrainingItemResult.objects.filter(recorded_by=duplicate).update(recorded_by=canonical)
