from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from iatrain.forms import PerspectiveForm, SportProfileForm
from iatrain.services import person_for_user, set_sport_profile_active

from .common import PERSPECTIVE_SESSION_KEY, safe_next


@login_required
@require_POST
def update_profile(request):
    person = person_for_user(request.user)
    if person is None or person.is_provisional:
        raise PermissionDenied
    form = SportProfileForm(request.POST)
    if form.is_valid():
        set_sport_profile_active(
            person=person,
            profile_type=form.cleaned_data["profile_type"],
            is_active=form.cleaned_data["active"],
        )
        messages.success(request, "Perfil esportiu actualitzat.")
    else:
        messages.error(request, "No s’ha pogut actualitzar el perfil esportiu.")
    return redirect(safe_next(request))


@login_required
@require_POST
def select_perspective(request):
    person = person_for_user(request.user)
    if person is None:
        raise PermissionDenied
    form = PerspectiveForm(request.POST, person=person)
    if not form.is_valid():
        raise PermissionDenied("Només pots seleccionar un perfil esportiu actiu.")
    request.session[PERSPECTIVE_SESSION_KEY] = form.cleaned_data["perspective"]
    return redirect("iatrain_home")
