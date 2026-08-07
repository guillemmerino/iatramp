from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from iatrain.forms import UnclaimedAthleteForm
from iatrain.models import AthleteProfile, TrainingGroupMembership
from iatrain.services import (
    accessible_athletes,
    create_unclaimed_athlete,
    has_athlete_access,
    managed_groups,
    person_for_user,
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
    memberships = TrainingGroupMembership.objects.filter(
        athlete_profile=profile,
        is_active=True,
        training_group__in=managed_groups(request.user),
    ).select_related("training_group__organization")
    context = base_context(request)
    context.update({"athlete_profile": profile, "athlete_memberships": memberships})
    return render(request, "iatrain/athletes/detail.html", context)
