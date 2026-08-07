"""Read-only queries for organizations and memberships."""

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from core.identity import person_for_user

from .models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
)


def current_membership_filter(on_date=None):
    on_date = on_date or timezone.localdate()
    return Q(
        status=Membership.Status.ACTIVE,
        start_date__lte=on_date,
        organization__is_active=True,
    ) & (Q(end_date__isnull=True) | Q(end_date__gte=on_date))


def reviewable_organizations_for_user(user):
    """Return active organizations where ``user`` can review requests."""
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
    """Return unresolved requests the user is authorized to review."""
    return OrganizationMembershipRequest.objects.filter(
        status=OrganizationMembershipRequest.Status.PENDING,
        organization__in=reviewable_organizations_for_user(user),
    )

