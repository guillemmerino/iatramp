"""IA Train-owned identity consolidation rules."""

from django.db.models import Q

from .models import (
    AthleteObservation,
    AthleteProfile,
    CoachAthleteRelation,
    CoachProfile,
    ElementNotation,
    ElementRotation,
    Gym,
    KnowledgeConcept,
    KnowledgeEditorialEvent,
    KnowledgeRelation,
    TrainingContext,
    TrainingGroup,
    TrainingGroupMembership,
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
