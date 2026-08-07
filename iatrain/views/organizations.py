from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from organizations.models import Organization
from iatrain.services import (
    accessible_athletes,
    accessible_gyms,
    managed_groups,
    organizations_available_to_coach,
)

from .common import base_context, require_coach


@login_required
def organization_list(request):
    require_coach(request)
    organizations = list(organizations_available_to_coach(request.user))
    groups = managed_groups(request.user).filter(is_active=True)
    gyms = accessible_gyms(request.user)
    for organization in organizations:
        organization.coach_group_count = groups.filter(organization=organization).count()
        organization.coach_athlete_count = accessible_athletes(
            request.user,
            permission="can_view_training",
            organization=organization,
        ).count()
        organization.coach_gym_count = gyms.filter(organizations=organization).count()
    context = base_context(request)
    context["iatrain_organizations"] = organizations
    return render(request, "iatrain/organizations/list.html", context)


@login_required
def organization_detail(request, slug):
    require_coach(request)
    try:
        organization = organizations_available_to_coach(request.user).get(slug=slug)
    except Organization.DoesNotExist:
        raise Http404
    context = base_context(request)
    context.update(
        {
            "organization": organization,
            "iatrain_groups": managed_groups(request.user)
            .filter(organization=organization, is_active=True)
            .prefetch_related("memberships"),
            "iatrain_athletes": accessible_athletes(
                request.user,
                permission="can_view_training",
                organization=organization,
            ).order_by("last_name", "first_name"),
            "iatrain_gyms": accessible_gyms(request.user)
            .filter(organizations=organization)
            .prefetch_related("equipment"),
        }
    )
    return render(request, "iatrain/organizations/detail.html", context)
