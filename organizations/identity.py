"""Organization-side integration for identity consolidation."""

from .models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
    OrganizationMembershipRequestRole,
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
                target_permission.delete()

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


def merge_organization_identity(*, canonical, duplicate):
    """Retarget all organization data while Core merges two people."""
    Organization.objects.filter(created_by=duplicate).update(created_by=canonical)
    Membership.objects.filter(approved_by=duplicate).update(approved_by=canonical)
    MembershipRole.objects.filter(granted_by=duplicate).update(granted_by=canonical)
    MembershipPermission.objects.filter(granted_by=duplicate).update(granted_by=canonical)
    OrganizationMembershipRequest.objects.filter(resolved_by=duplicate).update(
        resolved_by=canonical
    )
    _merge_memberships(canonical=canonical, duplicate=duplicate)
    _merge_membership_requests(canonical=canonical, duplicate=duplicate)

