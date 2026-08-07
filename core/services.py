import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from organizations.identity import merge_organization_identity

from .identity import person_for_user
from .models import (
    Person,
    PersonClaimInvitation,
    PersonMergeRecord,
)


def _merge_training_profiles(*, canonical, duplicate):
    from iatrain.models import (
        AthleteObservation,
        AthleteProfile,
        CoachAthleteRelation,
        CoachProfile,
        KnowledgeConcept,
        KnowledgeRelation,
        TrainingContext,
        TrainingGroupMembership,
    )

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

    relations = CoachAthleteRelation.objects.select_for_update().filter(
        Q(coach_profile=duplicate_coach) | Q(athlete_profile=duplicate_athlete)
    ) if duplicate_coach or duplicate_athlete else CoachAthleteRelation.objects.none()
    for source in list(relations):
        new_coach = canonical_coach if source.coach_profile_id == getattr(duplicate_coach, "pk", None) else source.coach_profile
        new_athlete = canonical_athlete if source.athlete_profile_id == getattr(duplicate_athlete, "pk", None) else source.athlete_profile
        if new_coach.person_id == new_athlete.person_id:
            source.delete()
            continue
        target = CoachAthleteRelation.objects.select_for_update().filter(
            coach_profile=new_coach,
            athlete_profile=new_athlete,
            organization=source.organization,
            function=source.function,
        ).exclude(pk=source.pk).first()
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

    if duplicate_athlete is not None:
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

        canonical_athlete.settings = {**duplicate_athlete.settings, **canonical_athlete.settings}
        canonical_athlete.extracted_facts = [
            *duplicate_athlete.extracted_facts,
            *canonical_athlete.extracted_facts,
        ]
        canonical_athlete.is_active = canonical_athlete.is_active or duplicate_athlete.is_active
        canonical_athlete.save()
        duplicate_athlete.delete()
    if duplicate_coach is not None:
        canonical_coach.settings = {**duplicate_coach.settings, **canonical_coach.settings}
        canonical_coach.is_active = canonical_coach.is_active or duplicate_coach.is_active
        canonical_coach.save()
        duplicate_coach.delete()

    TrainingContext.objects.filter(responsible_coach=duplicate).update(
        responsible_coach=canonical
    )
    for training_context in TrainingContext.objects.filter(athletes=duplicate):
        training_context.athletes.add(canonical)
        training_context.athletes.remove(duplicate)
    KnowledgeConcept.objects.filter(authored_by=duplicate).update(authored_by=canonical)
    KnowledgeRelation.objects.filter(authored_by=duplicate).update(authored_by=canonical)
    AthleteObservation.objects.filter(athlete=duplicate).update(athlete=canonical)
    AthleteObservation.objects.filter(authored_by=duplicate).update(authored_by=canonical)


@transaction.atomic
def merge_people(*, canonical, duplicate, merged_by=None):
    """Merge ``duplicate`` into ``canonical`` while preserving known domain history."""
    if canonical.pk == duplicate.pk:
        return Person.objects.select_for_update().get(pk=canonical.pk)
    locked = {
        item.pk: item
        for item in Person.objects.select_for_update().filter(
            pk__in=(canonical.pk, duplicate.pk)
        )
    }
    canonical = locked[canonical.pk]
    duplicate = locked[duplicate.pk]
    if canonical.user_id and duplicate.user_id and canonical.user_id != duplicate.user_id:
        raise ValidationError("No es poden fusionar identitats vinculades a comptes diferents.")

    duplicate_snapshot = {
        "id": duplicate.pk,
        "first_name": duplicate.first_name,
        "last_name": duplicate.last_name,
        "preferred_name": duplicate.preferred_name,
        "birth_date": duplicate.birth_date.isoformat() if duplicate.birth_date else None,
        "email": duplicate.email,
        "phone": duplicate.phone,
        "user_id": duplicate.user_id,
    }
    target_user_id = canonical.user_id or duplicate.user_id
    if duplicate.user_id:
        duplicate.user = None
        duplicate.save(update_fields=("user", "updated_at"))

    for field in ("first_name", "last_name", "preferred_name", "email", "phone"):
        if not getattr(canonical, field) and getattr(duplicate, field):
            setattr(canonical, field, getattr(duplicate, field))
    canonical.birth_date = canonical.birth_date or duplicate.birth_date
    canonical.user_id = target_user_id
    canonical.is_provisional = canonical.is_provisional and duplicate.is_provisional
    canonical.is_active = canonical.is_active or duplicate.is_active
    canonical.full_clean()
    canonical.save()

    merge_organization_identity(canonical=canonical, duplicate=duplicate)
    PersonClaimInvitation.objects.filter(created_by=duplicate).update(created_by=canonical)
    PersonClaimInvitation.objects.filter(person=duplicate).update(person=canonical)
    PersonMergeRecord.objects.filter(canonical_person=duplicate).update(
        canonical_person=canonical
    )
    _merge_training_profiles(canonical=canonical, duplicate=duplicate)

    duplicate_id = duplicate.pk
    duplicate.delete()
    PersonMergeRecord.objects.create(
        canonical_person=canonical,
        duplicate_person_id=duplicate_id,
        duplicate_snapshot=duplicate_snapshot,
        merged_by=merged_by,
    )
    return canonical


@transaction.atomic
def link_person_to_user(*, person, user):
    """Claim an existing identity, merging the account's provisional identity if needed."""
    target = Person.objects.select_for_update().get(pk=person.pk)
    if target.user_id and target.user_id != user.pk:
        raise ValidationError("La persona ja està vinculada a un altre compte.")
    current = Person.objects.select_for_update().filter(user=user).first()
    if current is not None and current.pk != target.pk:
        if current.is_provisional and not target.is_provisional:
            target = merge_people(canonical=target, duplicate=current, merged_by=user)
        else:
            target = merge_people(canonical=current, duplicate=target, merged_by=user)
    target.user = user
    target.is_provisional = False
    target.is_active = True
    target.full_clean()
    target.save(update_fields=("user", "is_provisional", "is_active", "updated_at"))
    return target


def _claim_token_digest(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


@transaction.atomic
def create_person_claim_invitation(*, person, email, created_by=None, expires_at=None):
    if person.user_id:
        raise ValidationError("La persona ja té un compte vinculat.")
    normalized_email = str(email or "").strip().lower()
    if not normalized_email:
        raise ValidationError({"email": "Cal indicar el correu de la persona convidada."})
    PersonClaimInvitation.objects.filter(
        person=person,
        email__iexact=normalized_email,
        status=PersonClaimInvitation.Status.PENDING,
    ).update(status=PersonClaimInvitation.Status.CANCELLED)
    raw_token = secrets.token_urlsafe(32)
    invitation = PersonClaimInvitation.objects.create(
        person=person,
        email=normalized_email,
        token_digest=_claim_token_digest(raw_token),
        created_by=created_by,
        expires_at=expires_at or timezone.now() + timedelta(days=14),
    )
    return invitation, raw_token


@transaction.atomic
def accept_person_claim_invitation(*, user, token):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Cal iniciar sessió per reclamar aquesta identitat.")
    invitation = (
        PersonClaimInvitation.objects.select_for_update()
        .select_related("person")
        .filter(token_digest=_claim_token_digest(token))
        .first()
    )
    if invitation is None:
        raise ValidationError("La invitació no és vàlida.")
    if invitation.status != PersonClaimInvitation.Status.PENDING:
        raise ValidationError("La invitació ja no està pendent.")
    if invitation.expires_at <= timezone.now():
        invitation.status = PersonClaimInvitation.Status.EXPIRED
        invitation.save(update_fields=("status", "updated_at"))
        raise ValidationError("La invitació ha caducat.")
    if not user.is_superuser and str(user.email or "").strip().lower() != invitation.email:
        raise ValidationError("El correu del compte no coincideix amb la invitació.")
    canonical = link_person_to_user(person=invitation.person, user=user)
    invitation.person = canonical
    invitation.status = PersonClaimInvitation.Status.CLAIMED
    invitation.claimed_by = user
    invitation.claimed_at = timezone.now()
    invitation.save(
        update_fields=("person", "status", "claimed_by", "claimed_at", "updated_at")
    )
    return canonical


def set_coach_athlete_relation(
    *,
    coach,
    athlete,
    function=None,
    organization=None,
    start_date=None,
    end_date=None,
    is_active=True,
    can_view_profile=True,
    can_view_training=True,
    can_edit_training=False,
    can_view_health_data=False,
    notes="",
):
    """Compatibility wrapper; training relationships belong to ``iatrain``."""
    from iatrain.services import set_coach_athlete_relation as set_relation

    kwargs = {
        "coach": coach,
        "athlete": athlete,
        "organization": organization,
        "start_date": start_date,
        "end_date": end_date,
        "is_active": is_active,
        "can_view_profile": can_view_profile,
        "can_view_training": can_view_training,
        "can_edit_training": can_edit_training,
        "can_view_health_data": can_view_health_data,
        "notes": notes,
    }
    if function is not None:
        kwargs["function"] = function
    return set_relation(**kwargs)


def has_athlete_access(user, athlete, permission="can_view_profile", organization=None):
    """Compatibility wrapper; athlete access belongs to ``iatrain``."""
    from iatrain.services import has_athlete_access as training_access

    return training_access(
        user,
        athlete,
        permission=permission,
        organization=organization,
    )


# Phase 1 compatibility facade. Organization behavior is implemented by the
# dedicated domain package; existing ``core.services`` imports remain valid
# until callers have migrated and the physical models move in phase 2.
from organizations.policies import (  # noqa: E402,F401
    ORGANIZATION_PERMISSION_DEFAULTS,
    REQUESTABLE_ORGANIZATION_ROLES,
    can_manage_organization,
    effective_membership_permissions,
    has_organization_permission,
    has_organization_role,
)
from organizations.selectors import (  # noqa: E402,F401
    current_membership_filter,
    reviewable_membership_requests_for_user,
    reviewable_organizations_for_user,
)
from organizations.services import (  # noqa: E402,F401
    cancel_organization_membership_request,
    create_organization_for_user,
    grant_membership,
    grant_membership_role,
    request_organization_membership,
    review_organization_membership_request,
    update_membership_access,
)
