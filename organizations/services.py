"""State-changing use cases for the organization domain."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from core.identity import person_for_user

from .models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
    OrganizationMembershipRequestRole,
)
from .policies import (
    REQUESTABLE_ORGANIZATION_ROLES,
    default_permissions_for_roles,
    has_organization_permission,
    has_organization_role,
)
from .selectors import current_membership_filter


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
    defaults = default_permissions_for_roles(desired_roles)
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

