from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render

from core.models import Organization
from iatrain.engine import build_training_selection
from iatrain.engine.forms import TrainingStartForm
from iatrain.services import accessible_gyms, managed_groups, organizations_available_to_coach
from iatrain.views.common import base_context, require_coach


@login_required
def training_start(request):
    require_coach(request)
    form = TrainingStartForm(request.POST or None, user=request.user)
    selection = None
    if request.method == "POST" and form.is_valid():
        selection = build_training_selection(
            organization=form.cleaned_data["organization"],
            training_group=form.cleaned_data["training_group"],
            gym=form.cleaned_data["gym"],
            additional_athletes=form.cleaned_data["additional_athletes"],
        )
    context = base_context(request)
    context.update({"form": form, "training_selection": selection})
    return render(request, "iatrain/engine/start.html", context)


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
