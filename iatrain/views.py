from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    GroupMemberForm,
    PerspectiveForm,
    SportProfileForm,
    TrainingGroupForm,
    UnclaimedAthleteForm,
)
from .models import (
    AthleteObservation,
    AthleteProfile,
    CoachAthleteRelation,
    TrainingGroup,
    TrainingGroupMembership,
    TrainingContext,
)
from .services import (
    accessible_athletes,
    add_group_member,
    can_manage_group,
    create_training_group,
    create_unclaimed_athlete,
    has_athlete_access,
    managed_groups,
    person_for_user,
    remove_group_member,
    set_sport_profile_active,
)


PERSPECTIVE_SESSION_KEY = "iatrain_perspective"


def _safe_next(request, fallback="iatrain_home"):
    target = request.POST.get("next")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def _profiles(person):
    profiles = {}
    if person:
        for key, related_name in (("athlete", "athlete_profile"), ("coach", "coach_profile")):
            try:
                profiles[key] = getattr(person, related_name)
            except ObjectDoesNotExist:
                profiles[key] = None
    return profiles


def _perspective(request, person, profiles):
    active = [key for key, profile in profiles.items() if profile and profile.is_active]
    selected = request.session.get(PERSPECTIVE_SESSION_KEY)
    if selected not in active:
        selected = "coach" if "coach" in active else (active[0] if active else None)
        if selected:
            request.session[PERSPECTIVE_SESSION_KEY] = selected
        else:
            request.session.pop(PERSPECTIVE_SESSION_KEY, None)
    return selected


def _base_context(request):
    person = person_for_user(request.user)
    profiles = _profiles(person)
    perspective = _perspective(request, person, profiles) if person else None
    return {
        "iatrain_person": person,
        "sport_profiles": profiles,
        "perspective": perspective,
    }


def home(request):
    context = _base_context(request)
    person = context["iatrain_person"]
    if not person or person.is_provisional or not context["perspective"]:
        return render(request, "iatrain/home.html", context)

    if context["perspective"] == "coach":
        athletes = accessible_athletes(request.user, permission="can_view_training").order_by(
            "last_name", "first_name"
        )
        groups = managed_groups(request.user).filter(is_active=True).select_related("organization")
        training_athletes = accessible_athletes(request.user, permission="can_view_training")
        contexts = TrainingContext.objects.filter(
            Q(responsible_coach=person) | Q(athletes__in=training_athletes)
        ).distinct()[:6]
        observations = AthleteObservation.objects.filter(athlete__in=training_athletes).select_related(
            "athlete", "authored_by"
        )[:8]
        context.update({"iatrain_athletes": athletes[:8], "iatrain_groups": groups[:8], "iatrain_contexts": contexts, "iatrain_observations": observations})
    else:
        athlete_profile = context["sport_profiles"]["athlete"]
        active_memberships = TrainingGroupMembership.objects.filter(
            athlete_profile=athlete_profile, is_active=True, training_group__is_active=True
        ).select_related("training_group__organization")
        today = timezone.localdate()
        today_relations = CoachAthleteRelation.objects.filter(
            athlete_profile=athlete_profile,
            is_active=True,
            coach_profile__is_active=True,
            start_date__lte=today,
        ).filter(Q(end_date__isnull=True) | Q(end_date__gte=today)).select_related("coach_profile__person", "organization")
        observations = AthleteObservation.objects.filter(athlete=person).select_related(
            "concept", "authored_by", "training_context"
        )[:10]
        context.update(
            {
                "athlete_memberships": active_memberships,
                "athlete_relations": today_relations,
                "iatrain_observations": observations,
            }
        )
    return render(request, "iatrain/home.html", context)


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
    return redirect(_safe_next(request))


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
    return redirect(_safe_next(request))


def _require_coach(request):
    if not request.user.is_authenticated:
        raise PermissionDenied
    person = person_for_user(request.user)
    try:
        valid = person and person.coach_profile.is_active
    except ObjectDoesNotExist:
        valid = False
    if not valid:
        raise PermissionDenied("Cal un perfil d’entrenador actiu.")
    return person


@login_required
def athlete_list(request):
    _require_coach(request)
    athletes = accessible_athletes(request.user, permission="can_view_profile")
    query = request.GET.get("q", "").strip()
    if query:
        athletes = athletes.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(preferred_name__icontains=query)
            | Q(email__icontains=query)
        )
    context = _base_context(request)
    context.update({"iatrain_athletes": athletes.order_by("last_name", "first_name"), "query": query})
    return render(request, "iatrain/athlete_list.html", context)


@login_required
def athlete_create(request):
    _require_coach(request)
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
    context = _base_context(request)
    context["form"] = form
    return render(request, "iatrain/form.html", {**context, "form_title": "Afegir gimnasta", "submit_label": "Crear gimnasta"})


@login_required
def athlete_detail(request, pk):
    _require_coach(request)
    profile = get_object_or_404(AthleteProfile.objects.select_related("person"), pk=pk)
    if not has_athlete_access(request.user, profile, permission="can_view_profile"):
        raise PermissionDenied
    memberships = TrainingGroupMembership.objects.filter(
        athlete_profile=profile,
        is_active=True,
        training_group__in=managed_groups(request.user),
    ).select_related("training_group__organization")
    context = _base_context(request)
    context.update({"athlete_profile": profile, "athlete_memberships": memberships})
    return render(request, "iatrain/athlete_detail.html", context)


@login_required
def group_list(request):
    _require_coach(request)
    context = _base_context(request)
    context["iatrain_groups"] = managed_groups(request.user).select_related("organization").prefetch_related(
        Prefetch("memberships", queryset=TrainingGroupMembership.objects.filter(is_active=True))
    )
    return render(request, "iatrain/group_list.html", context)


@login_required
def group_create(request):
    _require_coach(request)
    form = TrainingGroupForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        group = create_training_group(user=request.user, **form.cleaned_data)
        messages.success(request, "Grup creat.")
        return redirect("iatrain_group_detail", pk=group.pk)
    context = _base_context(request)
    context["form"] = form
    return render(request, "iatrain/form.html", {**context, "form_title": "Crear grup", "submit_label": "Crear grup"})


@login_required
def group_detail(request, pk):
    _require_coach(request)
    group = get_object_or_404(TrainingGroup.objects.select_related("organization"), pk=pk)
    if not can_manage_group(request.user, group):
        raise PermissionDenied
    form = GroupMemberForm(request.POST or None, user=request.user, organization=group.organization)
    if request.method == "POST" and form.is_valid():
        add_group_member(user=request.user, training_group=group, athlete_profile=form.cleaned_data["athlete"])
        messages.success(request, "Gimnasta afegit al grup.")
        return redirect("iatrain_group_detail", pk=group.pk)
    memberships = group.memberships.filter(is_active=True).select_related("athlete_profile__person")
    context = _base_context(request)
    context.update({"training_group": group, "memberships": memberships, "form": form})
    return render(request, "iatrain/group_detail.html", context)


@login_required
@require_POST
def group_member_remove(request, pk, membership_pk):
    _require_coach(request)
    membership = get_object_or_404(
        TrainingGroupMembership.objects.select_related("training_group"),
        pk=membership_pk,
        training_group_id=pk,
    )
    remove_group_member(user=request.user, membership=membership)
    messages.success(request, "Gimnasta retirat del grup; l’historial s’ha conservat.")
    return redirect("iatrain_group_detail", pk=pk)
