from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.text import slugify

from organizations.models import Organization
from iatrain.engine import build_training_selection
from iatrain.engine.forms import TrainingStartForm
from iatrain.services import accessible_gyms, managed_groups, organizations_available_to_coach
from iatrain.models import SessionGoal, SessionParticipantPlan, TrainingSession
from iatrain.training.services import create_session_revision, create_training_session
from iatrain.views.common import base_context, require_coach


@login_required
def training_start(request):
    require_coach(request)
    initial = {}
    if request.method == "GET":
        if request.GET.get("organization"):
            initial["organization"] = request.GET.get("organization")
        if request.GET.get("athlete"):
            initial["additional_athletes"] = [request.GET.get("athlete")]
    form = TrainingStartForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        selection = build_training_selection(
            organization=form.cleaned_data["organization"],
            training_group=form.cleaned_data["training_group"],
            gym=form.cleaned_data["gym"],
            additional_athletes=form.cleaned_data["additional_athletes"],
        )
        if not selection.athletes:
            form.add_error("training_group", "El grup no té gimnastes actius.")
        else:
            return _create_session_draft(request, form, selection)
    context = base_context(request)
    context.update({"form": form})
    return render(request, "iatrain/engine/start.html", context)


def _create_session_draft(request, form, selection):
    session = create_training_session(
        user=request.user,
        organization=selection.organization,
        scheduled_start=form.cleaned_data["scheduled_start"],
        expected_duration_minutes=form.cleaned_data["duration_minutes"],
        discipline=form.cleaned_data["discipline"],
        session_scope=(
            TrainingSession.Scope.GROUP
            if selection.training_group
            else TrainingSession.Scope.INDIVIDUAL
        ),
        gym=selection.gym,
        training_group=selection.training_group,
    )
    revision = create_session_revision(
        user=request.user,
        session=session,
        title=form.cleaned_data["title"],
        general_objective=form.cleaned_data["objective"],
        planned_duration_minutes=form.cleaned_data["duration_minutes"],
    )
    for athlete in selection.athletes:
        SessionParticipantPlan.objects.create(
            session_revision=revision,
            athlete_profile=athlete,
        )
    SessionGoal.objects.create(
        session_revision=revision,
        domain=SessionGoal.Domain.PHYSICAL,
        code=slugify(form.cleaned_data["objective"])[:80] or "objectiu-principal",
        description=form.cleaned_data["objective"],
        priority=SessionGoal.Priority.PRIMARY,
        source=SessionGoal.Source.COACH,
    )
    return redirect("iatrain_session_detail", pk=session.pk)


@login_required
def context_options(request):
    require_coach(request)
    organization_id = request.GET.get("organization")
    try:
        organization = organizations_available_to_coach(request.user).get(pk=organization_id)
    except (Organization.DoesNotExist, TypeError, ValueError):
        raise Http404
    groups = managed_groups(request.user).filter(
        organization=organization,
        is_active=True,
    ).order_by("name")
    gyms = accessible_gyms(request.user).filter(
        organization_links__organization=organization,
        organization_links__is_active=True,
    ).order_by("name")
    return JsonResponse(
        {
            "groups": [{"id": group.pk, "label": group.name} for group in groups],
            "gyms": [{"id": gym.pk, "label": gym.name} for gym in gyms],
        }
    )
