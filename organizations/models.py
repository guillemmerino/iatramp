"""Public model API for the organization domain.

The concrete models deliberately remain in ``core.models`` during phase 1.
Keeping this compatibility facade lets feature modules depend on the domain
boundary now, while preserving the current app labels, tables and migrations.
"""

from core.models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
    OrganizationMembershipRequestRole,
)

__all__ = (
    "Membership",
    "MembershipPermission",
    "MembershipRole",
    "Organization",
    "OrganizationMembershipRequest",
    "OrganizationMembershipRequestRole",
)

