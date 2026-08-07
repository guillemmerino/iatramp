import hashlib
import secrets
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils.text import slugify
from django.utils import timezone

from .models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
    OrganizationMembershipRequestRole,
    Person,
    PersonClaimInvitation,
    PersonMergeRecord,
)


ORGANIZATION_PERMISSION_DEFAULTS = {
    MembershipRole.Role.OWNER: frozenset(MembershipPermission.Permission.values),
    MembershipRole.Role.ADMIN: frozenset(MembershipPermission.Permission.values),
}
REQUESTABLE_ORGANIZATION_ROLES = frozenset(
    {
        MembershipRole.Role.COACH,
        MembershipRole.Role.ATHLETE,
        MembershipRole.Role.JUDGE,
        MembershipRole.Role.STAFF,
        MembershipRole.Role.MEMBER,
    }
)


def person_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        person = user.person
    except Person.DoesNotExist:
        return None
    return person if person.is_active else None


def current_membership_filter(on_date=None):
    on_date = on_date or timezone.localdate()
    return Q(
        status=Membership.Status.ACTIVE,
        start_date__lte=on_date,
        organization__is_active=True,
    ) & (Q(end_date__isnull=True) | Q(end_date__gte=on_date))


def _default_permissions_for_roles(roles):
    permissions = set()
    for role in roles:
        permissions.update(ORGANIZATION_PERMISSION_DEFAULTS.get(role, ()))
    return permissions


def effective_membership_permissions(membership):
    active_roles = set(
        membership.roles.filter(is_active=True).values_list("role", flat=True)
    )
    if MembershipRole.Role.OWNER in active_roles:
        return set(MembershipPermission.Permission.values)
    permissions = _default_permissions_for_roles(active_roles)
    for override in membership.permission_overrides.all():
        if override.is_allowed:
            permissions.add(override.permission)
        else:
            permissions.discard(override.permission)
    return permissions


def reviewable_organizations_for_user(user):
    """Return active organizations where ``user`` can review membership requests."""
    if not getattr(user, "is_authenticated", False):
        return Organization.objects.none()
    if user.is_superuser:
        return Organization.objects.filter(is_active=True)
    person = person_for_user(user)
    if person is None:
        return Organization.objects.none()

    active_roles = MembershipRole.objects.filter(
        membership_id=OuterRef("pk"),
        is_active=True,
    )
    review_overrides = MembershipPermission.objects.filter(
        membership_id=OuterRef("pk"),
        permission=MembershipPermission.Permission.REVIEW_REQUESTS,
    )
    memberships = (
        Membership.objects.filter(person=person)
        .filter(current_membership_filter())
        .annotate(
            has_owner=Exists(active_roles.filter(role=MembershipRole.Role.OWNER)),
            has_admin=Exists(active_roles.filter(role=MembershipRole.Role.ADMIN)),
            review_allowed=Exists(review_overrides.filter(is_allowed=True)),
            review_denied=Exists(review_overrides.filter(is_allowed=False)),
        )
        .filter(
            Q(has_owner=True)
            | Q(review_allowed=True)
            | Q(has_admin=True, review_denied=False)
        )
        .values("organization_id")
    )
    return Organization.objects.filter(is_active=True, pk__in=memberships)


def reviewable_membership_requests_for_user(user):
    """Return unresolved requests the user is currently authorized to review."""
    return OrganizationMembershipRequest.objects.filter(
        status=OrganizationMembershipRequest.Status.PENDING,
        organization__in=reviewable_organizations_for_user(user),
    )


def _merge_memberships(*, canonical, duplicate):
    for source in list(
        Membership.objects.select_for_update()
        .filter(person=duplicate)
        .prefetch_related("roles", "permission_overrides")
    ):
        target = Membership.objects.select_for_update().filter(
            person=canonical,
            organization=source.organization,
        ).first()
        if target is None:
            source.person = canonical
            source.save(update_fields=("person", "updated_at"))
            continue

        for role in source.roles.all():
            target_role = target.roles.filter(role=role.role).first()
            if target_role is None:
                role.membership = target
                role.save(update_fields=("membership", "updated_at"))
            else:
                target_role.is_active = target_role.is_active or role.is_active
                target_role.title = target_role.title or role.title
                target_role.granted_by = target_role.granted_by or role.granted_by
                target_role.save()
                role.delete()
        for permission in source.permission_overrides.all():
            target_permission = target.permission_overrides.filter(
                permission=permission.permission
            ).first()
            if target_permission is None:
                permission.membership = target
                permission.save(update_fields=("membership", "updated_at"))
            else:
                permission.delete()

        target.start_date = min(target.start_date, source.start_date)
        if target.end_date is None or source.end_date is None:
            target.end_date = None
        else:
            target.end_date = max(target.end_date, source.end_date)
        if source.status == Membership.Status.ACTIVE:
            target.status = Membership.Status.ACTIVE
        target.approved_at = target.approved_at or source.approved_at
        target.approved_by = target.approved_by or source.approved_by
        target.save()
        source.delete()


def _merge_membership_requests(*, canonical, duplicate):
    for source in list(
        OrganizationMembershipRequest.objects.select_for_update()
        .filter(person=duplicate)
        .prefetch_related("requested_roles")
    ):
        target = None
        if source.status == OrganizationMembershipRequest.Status.PENDING:
            target = OrganizationMembershipRequest.objects.select_for_update().filter(
                person=canonical,
                organization=source.organization,
                status=OrganizationMembershipRequest.Status.PENDING,
            ).first()
        if target is None:
            source.person = canonical
            source.save(update_fields=("person", "updated_at"))
            continue
        for requested_role in source.requested_roles.all():
            OrganizationMembershipRequestRole.objects.get_or_create(
                request=target,
                role=requested_role.role,
            )
        if source.message and source.message not in target.message:
            target.message = "\n\n".join(filter(None, (target.message, source.message)))
            target.save(update_fields=("message", "updated_at"))
        source.delete()


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

    Organization.objects.filter(created_by=duplicate).update(created_by=canonical)
    Membership.objects.filter(approved_by=duplicate).update(approved_by=canonical)
    MembershipRole.objects.filter(granted_by=duplicate).update(granted_by=canonical)
    MembershipPermission.objects.filter(granted_by=duplicate).update(granted_by=canonical)
    OrganizationMembershipRequest.objects.filter(resolved_by=duplicate).update(
        resolved_by=canonical
    )
    PersonClaimInvitation.objects.filter(created_by=duplicate).update(created_by=canonical)
    PersonClaimInvitation.objects.filter(person=duplicate).update(person=canonical)
    PersonMergeRecord.objects.filter(canonical_person=duplicate).update(
        canonical_person=canonical
    )
    _merge_memberships(canonical=canonical, duplicate=duplicate)
    _merge_membership_requests(canonical=canonical, duplicate=duplicate)
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


@transaction.atomic
def grant_membership(
    *,
    person,
    organization,
    role=MembershipRole.Role.MEMBER,
    title="",
    start_date=None,
    end_date=None,
    is_active=True,
    approved_by=None,
):
    membership = Membership.objects.select_for_update().filter(
        person=person,
        organization=organization,
    ).first()
    if membership is None:
        membership = Membership(person=person, organization=organization)
    membership.start_date = start_date or timezone.localdate()
    membership.end_date = end_date
    membership.status = Membership.Status.ACTIVE if is_active else Membership.Status.SUSPENDED
    membership.approved_at = membership.approved_at or timezone.now()
    membership.approved_by = approved_by
    membership.full_clean()
    membership.save()
    grant_membership_role(
        membership=membership,
        role=role,
        title=title,
        granted_by=approved_by,
    )
    return membership


def grant_membership_role(*, membership, role, title="", granted_by=None):
    if role not in MembershipRole.Role.values:
        raise ValidationError({"role": "El rol d'organització no és vàlid."})
    assignment, _ = MembershipRole.objects.select_for_update().get_or_create(
        membership=membership,
        role=role,
        defaults={"title": title, "granted_by": granted_by},
    )
    assignment.title = title
    assignment.granted_by = granted_by or assignment.granted_by
    assignment.is_active = True
    assignment.full_clean()
    assignment.save()
    return assignment


@transaction.atomic
def create_organization_for_user(*, user, name, kind=Organization.Kind.CLUB):
    creator = person_for_user(user)
    if creator is None or creator.is_provisional:
        raise ValidationError("Cal completar el perfil personal abans de crear una organització.")
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValidationError({"name": "El nom de l'organització és obligatori."})
    if Organization.objects.filter(name__iexact=normalized_name, is_active=True).exists():
        raise ValidationError({"name": "Ja existeix una organització activa amb aquest nom."})

    base_slug = slugify(normalized_name) or "organitzacio"
    slug = base_slug
    suffix = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1

    organization = Organization(
        name=normalized_name,
        slug=slug,
        kind=kind,
        created_by=creator,
    )
    organization.full_clean()
    organization.save()
    grant_membership(
        person=creator,
        organization=organization,
        role=MembershipRole.Role.OWNER,
        approved_by=creator,
    )
    return organization


@transaction.atomic
def request_organization_membership(*, user, organization, roles, message=""):
    person = person_for_user(user)
    if person is None or person.is_provisional:
        raise ValidationError("Cal completar el perfil personal abans de demanar l'accés.")
    if Membership.objects.filter(
        person=person,
        organization=organization,
    ).filter(current_membership_filter()).exists():
        raise ValidationError("Ja ets membre actiu d'aquesta organització.")
    if OrganizationMembershipRequest.objects.filter(
        person=person,
        organization=organization,
        status=OrganizationMembershipRequest.Status.PENDING,
    ).exists():
        raise ValidationError("Ja tens una sol·licitud pendent per a aquesta organització.")

    requested_roles = set(roles or (MembershipRole.Role.MEMBER,))
    if not requested_roles.issubset(REQUESTABLE_ORGANIZATION_ROLES):
        raise ValidationError({"roles": "No pots sol·licitar rols administratius."})

    membership_request = OrganizationMembershipRequest(
        person=person,
        organization=organization,
        message=str(message or "").strip(),
    )
    membership_request.full_clean()
    membership_request.save()
    OrganizationMembershipRequestRole.objects.bulk_create(
        [
            OrganizationMembershipRequestRole(request=membership_request, role=role)
            for role in sorted(requested_roles)
        ]
    )
    return membership_request


@transaction.atomic
def cancel_organization_membership_request(*, user, membership_request):
    locked_request = OrganizationMembershipRequest.objects.select_for_update().get(
        pk=membership_request.pk
    )
    person = person_for_user(user)
    if person is None or locked_request.person_id != person.pk:
        raise PermissionDenied("No pots cancel·lar aquesta sol·licitud.")
    if locked_request.status != OrganizationMembershipRequest.Status.PENDING:
        raise ValidationError("La sol·licitud ja no està pendent.")
    locked_request.status = OrganizationMembershipRequest.Status.CANCELLED
    locked_request.resolved_by = person
    locked_request.resolved_at = timezone.now()
    locked_request.save(update_fields=("status", "resolved_by", "resolved_at", "updated_at"))
    return locked_request


@transaction.atomic
def review_organization_membership_request(*, user, membership_request, approve):
    locked_request = (
        OrganizationMembershipRequest.objects.select_for_update()
        .select_related("organization", "person")
        .get(pk=membership_request.pk)
    )
    if not has_organization_permission(
        user,
        locked_request.organization,
        MembershipPermission.Permission.REVIEW_REQUESTS,
    ):
        raise PermissionDenied("No pots revisar sol·licituds d'aquesta organització.")
    if locked_request.status != OrganizationMembershipRequest.Status.PENDING:
        raise ValidationError("La sol·licitud ja s'ha resolt.")

    reviewer = person_for_user(user)
    membership = None
    if approve:
        roles = list(locked_request.requested_roles.values_list("role", flat=True))
        if not set(roles).issubset(REQUESTABLE_ORGANIZATION_ROLES):
            raise ValidationError("La sol·licitud conté rols administratius no autoritzats.")
        membership = grant_membership(
            person=locked_request.person,
            organization=locked_request.organization,
            role=(roles or [MembershipRole.Role.MEMBER])[0],
            approved_by=reviewer,
        )
        for role in roles[1:]:
            grant_membership_role(
                membership=membership,
                role=role,
                granted_by=reviewer,
            )
        locked_request.status = OrganizationMembershipRequest.Status.APPROVED
    else:
        locked_request.status = OrganizationMembershipRequest.Status.REJECTED
    locked_request.resolved_by = reviewer
    locked_request.resolved_at = timezone.now()
    locked_request.save(update_fields=("status", "resolved_by", "resolved_at", "updated_at"))
    return membership


def has_organization_role(user, organization, role):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    person = person_for_user(user)
    if person is None:
        return False
    return MembershipRole.objects.filter(
        membership__person=person,
        membership__organization=organization,
        membership__in=Membership.objects.filter(current_membership_filter()),
        role=role,
        is_active=True,
    ).exists()


def has_organization_permission(user, organization, permission):
    if permission not in MembershipPermission.Permission.values:
        raise ValueError(f"Permís d'organització desconegut: {permission}")
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    person = person_for_user(user)
    if person is None:
        return False
    membership = (
        Membership.objects.filter(person=person, organization=organization)
        .filter(current_membership_filter())
        .prefetch_related("roles", "permission_overrides")
        .first()
    )
    if membership is None:
        return False
    active_roles = {role.role for role in membership.roles.all() if role.is_active}
    if MembershipRole.Role.OWNER in active_roles:
        return True
    override = next(
        (
            item
            for item in membership.permission_overrides.all()
            if item.permission == permission
        ),
        None,
    )
    if override is not None:
        return override.is_allowed
    return permission in _default_permissions_for_roles(active_roles)


@transaction.atomic
def update_membership_access(*, user, membership, roles, permissions):
    locked_membership = (
        Membership.objects.select_for_update()
        .select_related("organization", "person")
        .get(pk=membership.pk)
    )
    organization = locked_membership.organization
    if not has_organization_permission(
        user,
        organization,
        MembershipPermission.Permission.MANAGE_ROLES,
    ):
        raise PermissionDenied("No pots gestionar rols i permisos d'aquesta organització.")

    desired_roles = set(roles or (MembershipRole.Role.MEMBER,))
    if not desired_roles.issubset(set(MembershipRole.Role.values)):
        raise ValidationError({"roles": "Hi ha un rol d'organització desconegut."})
    current_roles = set(
        locked_membership.roles.filter(is_active=True).values_list("role", flat=True)
    )
    owner_change = (MembershipRole.Role.OWNER in current_roles) != (
        MembershipRole.Role.OWNER in desired_roles
    )
    if owner_change and not (
        user.is_superuser
        or has_organization_role(user, organization, MembershipRole.Role.OWNER)
    ):
        raise PermissionDenied("Només un responsable pot assignar o retirar el rol de responsable.")
    if MembershipRole.Role.OWNER in current_roles and MembershipRole.Role.OWNER not in desired_roles:
        other_owner_exists = MembershipRole.objects.filter(
            membership__organization=organization,
            membership__in=Membership.objects.filter(current_membership_filter()),
            role=MembershipRole.Role.OWNER,
            is_active=True,
        ).exclude(membership=locked_membership).exists()
        if not other_owner_exists:
            raise ValidationError("L'organització ha de conservar almenys un responsable actiu.")

    actor = person_for_user(user)
    for role in MembershipRole.Role.values:
        assignment = locked_membership.roles.filter(role=role).first()
        if role in desired_roles:
            if assignment is None:
                grant_membership_role(
                    membership=locked_membership,
                    role=role,
                    granted_by=actor,
                )
            elif not assignment.is_active:
                assignment.is_active = True
                assignment.granted_by = actor
                assignment.save(update_fields=("is_active", "granted_by", "updated_at"))
        elif assignment is not None and assignment.is_active:
            assignment.is_active = False
            assignment.save(update_fields=("is_active", "updated_at"))

    desired_permissions = set(permissions or ())
    if not desired_permissions.issubset(set(MembershipPermission.Permission.values)):
        raise ValidationError({"permissions": "Hi ha un permís d'organització desconegut."})
    defaults = _default_permissions_for_roles(desired_roles)
    if MembershipRole.Role.OWNER in desired_roles:
        desired_permissions = set(MembershipPermission.Permission.values)
    for permission in MembershipPermission.Permission.values:
        desired = permission in desired_permissions
        default = permission in defaults
        if desired == default:
            locked_membership.permission_overrides.filter(permission=permission).delete()
        else:
            MembershipPermission.objects.update_or_create(
                membership=locked_membership,
                permission=permission,
                defaults={"is_allowed": desired, "granted_by": actor},
            )
    return locked_membership


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


def can_manage_organization(user, organization):
    return has_organization_permission(
        user,
        organization,
        MembershipPermission.Permission.MANAGE_ORGANIZATION,
    )


def has_athlete_access(user, athlete, permission="can_view_profile", organization=None):
    """Compatibility wrapper; athlete access belongs to ``iatrain``."""
    from iatrain.services import has_athlete_access as training_access

    return training_access(
        user,
        athlete,
        permission=permission,
        organization=organization,
    )
