from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from django.utils import timezone

from .models import (
    CoachAthleteRelation,
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
    OrganizationMembershipRequestRole,
    Person,
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


@transaction.atomic
def link_person_to_user(*, person, user):
    """Link an existing person to an auth user without replacing another link."""
    locked_person = Person.objects.select_for_update().get(pk=person.pk)
    if locked_person.user_id and locked_person.user_id != user.pk:
        raise ValidationError("La persona ja està vinculada a un altre compte.")
    if Person.objects.filter(user=user).exclude(pk=locked_person.pk).exists():
        raise ValidationError("El compte ja està vinculat a una altra persona.")
    locked_person.user = user
    locked_person.full_clean()
    locked_person.save(update_fields=("user", "updated_at"))
    return locked_person


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
    if creator is None:
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
    if person is None:
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


@transaction.atomic
def set_coach_athlete_relation(
    *,
    coach,
    athlete,
    function=CoachAthleteRelation.Function.PRIMARY_COACH,
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
    relation = CoachAthleteRelation.objects.select_for_update().filter(
        coach=coach,
        athlete=athlete,
        organization=organization,
        function=function,
    ).first()
    if relation is None:
        relation = CoachAthleteRelation(
            coach=coach,
            athlete=athlete,
            organization=organization,
            function=function,
        )
    relation.start_date = start_date or timezone.localdate()
    relation.end_date = end_date
    relation.is_active = is_active
    relation.can_view_profile = can_view_profile
    relation.can_view_training = can_view_training
    relation.can_edit_training = can_edit_training
    relation.can_view_health_data = can_view_health_data
    relation.notes = notes
    relation.full_clean()
    relation.save()
    return relation


def can_manage_organization(user, organization):
    return has_organization_permission(
        user,
        organization,
        MembershipPermission.Permission.MANAGE_ORGANIZATION,
    )


def has_athlete_access(user, athlete, permission="can_view_profile", organization=None):
    """Return access granted by self-access or a current explicit coach relation."""
    allowed_permissions = {
        "can_view_profile",
        "can_view_training",
        "can_edit_training",
        "can_view_health_data",
    }
    if permission not in allowed_permissions:
        raise ValueError(f"Permís desconegut: {permission}")
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    person = getattr(user, "person", None)
    if person is None:
        return False
    if person.pk == athlete.pk:
        return True

    today = timezone.localdate()
    relations = CoachAthleteRelation.objects.filter(
        coach=person,
        athlete=athlete,
        is_active=True,
        start_date__lte=today,
        **{permission: True},
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    if organization is not None:
        relations = relations.filter(organization=organization)
    return relations.exists()
