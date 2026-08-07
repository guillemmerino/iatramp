from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from iatrain.models import (
    AthleteObservation,
    CoachAthleteRelation,
    TrainingGroupMembership,
    TrainingContext,
)
from iatrain.services import (
    accessible_athletes,
    accessible_gyms,
    managed_groups,
    organizations_available_to_coach,
)

from .common import base_context


def home(request):
    context = base_context(request)
    person = context["iatrain_person"]
    if not request.user.is_authenticated:
        return render(request, "iatrain/dashboard/landing.html", context)
    if not person or person.is_provisional:
        return render(request, "iatrain/dashboard/identity_pending.html", context)
    if not context["perspective"]:
        return render(request, "iatrain/dashboard/profile_setup.html", context)
    if context["perspective"] == "athlete":
        return _athlete_dashboard(request, context, person)
    return _coach_dashboard(request, context, person)


def _coach_dashboard(request, context, person):
    athletes = accessible_athletes(request.user, permission="can_view_training").order_by(
        "last_name", "first_name"
    )
    groups = managed_groups(request.user).filter(is_active=True).select_related("organization")
    organizations = list(organizations_available_to_coach(request.user))
    gyms = accessible_gyms(request.user).prefetch_related("equipment", "organizations")
    training_athletes = accessible_athletes(request.user, permission="can_view_training")
    contexts = TrainingContext.objects.filter(
        Q(responsible_coach=person) | Q(athletes__in=training_athletes)
    ).distinct()[:6]
    observations = AthleteObservation.objects.filter(athlete__in=training_athletes).select_related(
        "athlete", "authored_by"
    )[:8]
    for organization in organizations:
        organization.coach_group_count = groups.filter(organization=organization).count()
        organization.coach_athlete_count = accessible_athletes(
            request.user,
            permission="can_view_training",
            organization=organization,
        ).count()
        organization.coach_gym_count = gyms.filter(organizations=organization).count()
    context.update(
        {
            "iatrain_athletes": athletes[:6],
            "iatrain_groups": groups[:6],
            "iatrain_organizations": organizations[:4],
            "iatrain_gyms": gyms[:4],
            "iatrain_contexts": contexts,
            "iatrain_observations": observations,
            "coach_totals": {
                "organizations": len(organizations),
                "groups": groups.count(),
                "athletes": athletes.count(),
                "gyms": gyms.count(),
            },
        }
    )
    return render(request, "iatrain/dashboard/coach.html", context)


def _athlete_dashboard(request, context, person):
    athlete_profile = context["sport_profiles"]["athlete"]
    active_memberships = TrainingGroupMembership.objects.filter(
        athlete_profile=athlete_profile,
        is_active=True,
        training_group__is_active=True,
    ).select_related("training_group__organization")
    today = timezone.localdate()
    relations = CoachAthleteRelation.objects.filter(
        athlete_profile=athlete_profile,
        is_active=True,
        coach_profile__is_active=True,
        start_date__lte=today,
    ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).select_related(
        "coach_profile__person", "organization"
    )
    observations = AthleteObservation.objects.filter(athlete=person).select_related(
        "concept", "authored_by", "training_context"
    )[:10]
    context.update(
        {
            "athlete_memberships": active_memberships,
            "athlete_relations": relations,
            "iatrain_observations": observations,
        }
    )
    return render(request, "iatrain/dashboard/athlete.html", context)
