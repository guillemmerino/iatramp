from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from iatrain.forms import GymEquipmentForm, GymForm
from iatrain.models import Gym, GymEquipment
from iatrain.services import (
    accessible_gyms,
    can_manage_gym,
    create_gym,
    save_gym_equipment,
    update_gym,
)

from .common import base_context, require_coach


@login_required
def gym_list(request):
    require_coach(request)
    context = base_context(request)
    context["iatrain_gyms"] = accessible_gyms(request.user).prefetch_related(
        "organizations", "equipment"
    )
    return render(request, "iatrain/gyms/list.html", context)


@login_required
def gym_create(request):
    require_coach(request)
    form = GymForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        gym = create_gym(user=request.user, **form.cleaned_data)
        messages.success(request, "Gimnàs creat. Ara pots completar-ne el material.")
        return redirect("iatrain_gym_detail", pk=gym.pk)
    context = base_context(request)
    context.update({"form": form, "form_title": "Crear gimnàs", "submit_label": "Crear gimnàs"})
    return render(request, "iatrain/gyms/form.html", context)


@login_required
def gym_edit(request, pk):
    require_coach(request)
    gym = get_object_or_404(Gym, pk=pk)
    if not can_manage_gym(request.user, gym):
        raise PermissionDenied
    form = GymForm(request.POST or None, user=request.user, gym=gym)
    if request.method == "POST" and form.is_valid():
        update_gym(user=request.user, gym=gym, **form.cleaned_data)
        messages.success(request, "Gimnàs actualitzat.")
        return redirect("iatrain_gym_detail", pk=gym.pk)
    context = base_context(request)
    context.update({"form": form, "gym": gym, "form_title": "Editar gimnàs", "submit_label": "Desar canvis"})
    return render(request, "iatrain/gyms/form.html", context)


@login_required
def gym_detail(request, pk):
    require_coach(request)
    gym = get_object_or_404(
        accessible_gyms(request.user).prefetch_related("organizations", "equipment"),
        pk=pk,
    )
    context = base_context(request)
    context.update({"gym": gym, "equipment": gym.equipment.all()})
    return render(request, "iatrain/gyms/detail.html", context)


@login_required
def gym_equipment_create(request, pk):
    require_coach(request)
    gym = get_object_or_404(Gym, pk=pk)
    if not can_manage_gym(request.user, gym):
        raise PermissionDenied
    form = GymEquipmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        save_gym_equipment(user=request.user, gym=gym, **form.cleaned_data)
        messages.success(request, "Material afegit.")
        return redirect("iatrain_gym_detail", pk=gym.pk)
    context = base_context(request)
    context.update(
        {"form": form, "gym": gym, "form_title": "Afegir material", "submit_label": "Afegir material"}
    )
    return render(request, "iatrain/gyms/equipment_form.html", context)


@login_required
def gym_equipment_edit(request, pk, equipment_pk):
    require_coach(request)
    gym = get_object_or_404(Gym, pk=pk)
    if not can_manage_gym(request.user, gym):
        raise PermissionDenied
    equipment = get_object_or_404(GymEquipment, pk=equipment_pk, gym=gym)
    form = GymEquipmentForm(request.POST or None, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        save_gym_equipment(
            user=request.user,
            gym=gym,
            equipment=equipment,
            **form.cleaned_data,
        )
        messages.success(request, "Material actualitzat.")
        return redirect("iatrain_gym_detail", pk=gym.pk)
    context = base_context(request)
    context.update(
        {
            "form": form,
            "gym": gym,
            "equipment_item": equipment,
            "form_title": "Editar material",
            "submit_label": "Desar material",
        }
    )
    return render(request, "iatrain/gyms/equipment_form.html", context)
