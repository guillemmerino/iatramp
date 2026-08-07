from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from iatrain.forms import GroupMemberForm, TrainingGroupForm
from iatrain.models import TrainingGroup, TrainingGroupMembership
from iatrain.services import (
    add_group_member,
    can_manage_group,
    create_training_group,
    managed_groups,
    remove_group_member,
)

from .common import base_context, require_coach


@login_required
def group_list(request):
    require_coach(request)
    context = base_context(request)
    context["iatrain_groups"] = managed_groups(request.user).select_related("organization").prefetch_related(
        Prefetch("memberships", queryset=TrainingGroupMembership.objects.filter(is_active=True))
    )
    return render(request, "iatrain/groups/list.html", context)


@login_required
def group_create(request):
    require_coach(request)
    initial = {}
    if request.GET.get("organization"):
        initial["organization"] = request.GET["organization"]
    form = TrainingGroupForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        group = create_training_group(user=request.user, **form.cleaned_data)
        messages.success(request, "Grup creat.")
        return redirect("iatrain_group_detail", pk=group.pk)
    context = base_context(request)
    context.update({"form": form, "form_title": "Crear grup", "submit_label": "Crear grup"})
    return render(request, "iatrain/components/form.html", context)


@login_required
def group_detail(request, pk):
    require_coach(request)
    group = get_object_or_404(TrainingGroup.objects.select_related("organization"), pk=pk)
    if not can_manage_group(request.user, group):
        raise PermissionDenied
    form = GroupMemberForm(request.POST or None, user=request.user, organization=group.organization)
    if request.method == "POST" and form.is_valid():
        add_group_member(user=request.user, training_group=group, athlete_profile=form.cleaned_data["athlete"])
        messages.success(request, "Gimnasta afegit al grup.")
        return redirect("iatrain_group_detail", pk=group.pk)
    memberships = group.memberships.filter(is_active=True).select_related("athlete_profile__person")
    context = base_context(request)
    context.update({"training_group": group, "memberships": memberships, "form": form})
    return render(request, "iatrain/groups/detail.html", context)


@login_required
@require_POST
def group_member_remove(request, pk, membership_pk):
    require_coach(request)
    membership = get_object_or_404(
        TrainingGroupMembership.objects.select_related("training_group"),
        pk=membership_pk,
        training_group_id=pk,
    )
    remove_group_member(user=request.user, membership=membership)
    messages.success(request, "Gimnasta retirat del grup; l’historial s’ha conservat.")
    return redirect("iatrain_group_detail", pk=pk)
