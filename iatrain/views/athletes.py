from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify

from iatrain.athletes.context import build_athlete_profile_context
from iatrain.athletes.services import (
    propose_athlete_condition,
    record_athlete_measurement,
    set_athlete_sport_profile,
)
from iatrain.forms import (
    AthleteConditionForm,
    AthleteMeasurementForm,
    AthleteObservationForm,
    AthleteSportProfileForm,
    UnclaimedAthleteForm,
)
from iatrain.models import (
    AthleteCondition,
    AthleteInsight,
    AthleteMeasurement,
    AthleteProfile,
    TrainingGroupMembership,
)
from iatrain.services import (
    accessible_athletes,
    can_record_observations,
    create_unclaimed_athlete,
    has_athlete_access,
    managed_groups,
    organizations_available_to_coach,
    person_for_user,
    record_athlete_observation,
)

from .common import base_context, require_coach


@login_required
def athlete_list(request):
    require_coach(request)
    athletes = accessible_athletes(request.user, permission="can_view_profile")
    query = request.GET.get("q", "").strip()
    if query:
        athletes = athletes.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(preferred_name__icontains=query)
            | Q(email__icontains=query)
        )
    context = base_context(request)
    context.update({"iatrain_athletes": athletes.order_by("last_name", "first_name"), "query": query})
    return render(request, "iatrain/athletes/list.html", context)


@login_required
def athlete_create(request):
    require_coach(request)
    form = UnclaimedAthleteForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        athlete_profile, _, invitation, _ = create_unclaimed_athlete(
            coach=person_for_user(request.user), **form.cleaned_data
        )
        if invitation:
            messages.success(request, "Gimnasta creat i invitació preparada.")
        else:
            messages.success(request, "Gimnasta creat. Pots afegir el correu més endavant.")
        return redirect("iatrain_athlete_detail", pk=athlete_profile.pk)
    context = base_context(request)
    context.update({"form": form, "form_title": "Afegir gimnasta", "submit_label": "Crear gimnasta"})
    return render(request, "iatrain/components/form.html", context)


@login_required
def athlete_detail(request, pk):
    require_coach(request)
    profile = get_object_or_404(AthleteProfile.objects.select_related("person"), pk=pk)
    if not has_athlete_access(request.user, profile, permission="can_view_profile"):
        raise PermissionDenied
    organization_options = _athlete_organizations(request.user, profile)
    selected_organization = _selected_organization(
        request, organization_options
    )
    action = request.POST.get("action", "")
    active_tab = request.POST.get("active_tab") or request.GET.get("tab", "overview")

    sport_form = AthleteSportProfileForm(
        request.POST if action == "sport_profile" else None,
        prefix="sport",
    )
    measurement_form = AthleteMeasurementForm(
        request.POST if action == "measurement" else None,
        prefix="measurement",
    )
    observation_form = AthleteObservationForm(
        request.POST if action == "observation" else None,
        prefix="observation",
    )
    condition_form = AthleteConditionForm(
        request.POST if action == "condition" else None,
        prefix="condition",
    )

    if request.method == "POST" and action:
        target_form = {
            "sport_profile": sport_form,
            "measurement": measurement_form,
            "observation": observation_form,
            "condition": condition_form,
        }.get(action)
        if target_form is None:
            raise PermissionDenied
        if target_form.is_valid():
            try:
                _save_profile_action(
                    action=action,
                    form=target_form,
                    request=request,
                    profile=profile,
                    organization=selected_organization,
                )
            except (PermissionDenied, ValidationError) as error:
                target_form.add_error(None, error)
            else:
                messages.success(request, _success_message(action))
                return redirect(
                    _athlete_detail_url(
                        profile,
                        selected_organization,
                        _action_tab(action),
                    )
                )

    memberships = TrainingGroupMembership.objects.filter(
        athlete_profile=profile,
        is_active=True,
        training_group__in=managed_groups(request.user),
    ).select_related("training_group__organization")
    can_view_training = has_athlete_access(
        request.user,
        profile,
        permission="can_view_training",
        organization=selected_organization,
    )
    can_edit_profile = can_record_observations(
        request.user,
        profile.person,
        organization=selected_organization,
    )
    health_access = has_athlete_access(
        request.user,
        profile,
        permission="can_view_health_data",
        organization=selected_organization,
    )
    profile_context = None
    if can_view_training:
        try:
            profile_context = build_athlete_profile_context(
                user=request.user,
                athlete=profile,
                organization=selected_organization,
            )
        except (PermissionDenied, ValidationError):
            profile_context = None
    scope_filter = (
        Q(organization=selected_organization) | Q(organization__isnull=True)
        if selected_organization
        else Q()
    )
    measurements = profile.measurements.filter(scope_filter).select_related(
        "recorded_by"
    ).order_by("-measured_at", "-id")
    if not health_access:
        measurements = measurements.exclude(domain__in=("anthropometry", "recovery"))
    conditions = profile.conditions.none()
    if health_access:
        conditions = profile.conditions.filter(scope_filter).select_related(
            "body_region", "recorded_by", "confirmed_by"
        ).order_by("-started_at", "-id")
    observations = profile.person.training_observations.filter(
        superseded_by__isnull=True
    )
    if selected_organization:
        observations = observations.filter(
            Q(organization=selected_organization)
            | Q(organization__isnull=True, training_context__organization=selected_organization)
            | Q(organization__isnull=True, training_context__isnull=True)
        )
    observations = observations.select_related("authored_by", "concept").order_by(
        "-observed_at", "-id"
    )
    insights = profile.insights.filter(scope_filter).prefetch_related("evidence_links")
    if not health_access:
        insights = insights.exclude(kind=AthleteInsight.Kind.RISK_SIGNAL)
    insights = insights.order_by("-created_at", "-id")
    context = base_context(request)
    context.update(
        {
            "athlete_profile": profile,
            "athlete_memberships": memberships,
            "organization_options": organization_options,
            "selected_organization": selected_organization,
            "profile_context": profile_context,
            "can_view_training": can_view_training,
            "can_edit_profile": can_edit_profile,
            "health_access": health_access,
            "active_tab": active_tab,
            "sport_form": sport_form,
            "measurement_form": measurement_form,
            "observation_form": observation_form,
            "condition_form": condition_form,
            "sport_records": profile.sport_profiles.filter(is_active=True),
            "measurement_records": measurements,
            "condition_records": conditions,
            "observation_records": observations,
            "insight_records": insights,
            "training_responses": (
                profile_context["recent_training_responses"] if profile_context else []
            ),
        }
    )
    return render(request, "iatrain/athletes/detail.html", context)


def _athlete_organizations(user, profile):
    actor = person_for_user(user)
    available = organizations_available_to_coach(user)
    if getattr(user, "is_superuser", False):
        return available.filter(
            Q(training_relationships__athlete_profile=profile)
            | Q(training_groups__memberships__athlete_profile=profile)
            | Q(training_sessions__revisions__participant_plans__athlete_profile=profile)
        ).distinct().order_by("name")
    return available.filter(
        Q(
            training_relationships__athlete_profile=profile,
            training_relationships__coach_profile__person=actor,
            training_relationships__is_active=True,
        )
        | Q(
            training_groups__memberships__athlete_profile=profile,
            training_groups__managing_coaches__person=actor,
        )
    ).distinct().order_by("name")


def _selected_organization(request, options):
    raw_value = request.POST.get("organization_scope") or request.GET.get("organization")
    if raw_value:
        try:
            return options.get(pk=raw_value)
        except (TypeError, ValueError, options.model.DoesNotExist):
            raise PermissionDenied
    return options.first() if options.count() else None


def _save_profile_action(*, action, form, request, profile, organization):
    values = form.cleaned_data
    if action == "sport_profile":
        return set_athlete_sport_profile(
            user=request.user,
            athlete=profile,
            organization=organization,
            **values,
        )
    if action == "measurement":
        metric_code = values.pop("metric_code") or slugify(values["metric_label"])
        return record_athlete_measurement(
            user=request.user,
            athlete=profile,
            organization=organization,
            metric_code=metric_code,
            **values,
        )
    if action == "observation":
        return record_athlete_observation(
            user=request.user,
            athlete=profile.person,
            organization=organization,
            **values,
        )
    if action == "condition":
        return propose_athlete_condition(
            user=request.user,
            athlete=profile,
            organization=organization,
            **values,
        )
    raise PermissionDenied


def _action_tab(action):
    return {
        "sport_profile": "profile",
        "measurement": "measurements",
        "observation": "observations",
        "condition": "conditions",
    }[action]


def _success_message(action):
    return {
        "sport_profile": "Perfil esportiu actualitzat.",
        "measurement": "Mesura registrada.",
        "observation": "Observació registrada.",
        "condition": "Condició enviada a revisió.",
    }[action]


def _athlete_detail_url(profile, organization, tab):
    url = reverse("iatrain_athlete_detail", args=(profile.pk,))
    scope = f"&organization={organization.pk}" if organization else ""
    return f"{url}?tab={tab}{scope}"
