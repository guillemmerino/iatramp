"""Authorization rules for the organization domain."""

from core.identity import person_for_user

from .models import Membership, MembershipPermission, MembershipRole
from .selectors import current_membership_filter


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


def default_permissions_for_roles(roles):
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
    permissions = default_permissions_for_roles(active_roles)
    for override in membership.permission_overrides.all():
        if override.is_allowed:
            permissions.add(override.permission)
        else:
            permissions.discard(override.permission)
    return permissions


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
    return permission in default_permissions_for_roles(active_roles)


def can_manage_organization(user, organization):
    return has_organization_permission(
        user,
        organization,
        MembershipPermission.Permission.MANAGE_ORGANIZATION,
    )

