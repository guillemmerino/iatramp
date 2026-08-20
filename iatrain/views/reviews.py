from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from iatrain.athletes.services import (
    resolve_athlete_condition,
    review_athlete_condition,
    review_athlete_insight,
)
from iatrain.models import AthleteCondition, AthleteInsight
from iatrain.services import has_athlete_access

from .common import base_context, require_coach, safe_next


def _can_review_condition(user, condition):
    return has_athlete_access(
        user,
        condition.athlete_profile,
        permission="can_edit_training",
        organization=condition.organization,
    ) and has_athlete_access(
        user,
        condition.athlete_profile,
        permission="can_view_health_data",
        organization=condition.organization,
    )


def _can_review_insight(user, insight):
    can_edit = has_athlete_access(
        user,
        insight.athlete_profile,
        permission="can_edit_training",
        organization=insight.organization,
    )
    if insight.kind != AthleteInsight.Kind.RISK_SIGNAL:
        return can_edit
    return can_edit and has_athlete_access(
        user,
        insight.athlete_profile,
        permission="can_view_health_data",
        organization=insight.organization,
    )


@login_required
def profile_review(request):
    require_coach(request)
    athlete_id = request.GET.get("athlete")
    conditions = AthleteCondition.objects.filter(
        status=AthleteCondition.Status.PROPOSED
    ).select_related("athlete_profile__person", "organization", "body_region")
    insights = AthleteInsight.objects.filter(
        status=AthleteInsight.Status.PROPOSED
    ).select_related("athlete_profile__person", "organization").prefetch_related(
        "evidence_links"
    )
    if athlete_id:
        conditions = conditions.filter(athlete_profile_id=athlete_id)
        insights = insights.filter(athlete_profile_id=athlete_id)
    review_conditions = [
        condition for condition in conditions if _can_review_condition(request.user, condition)
    ]
    review_insights = [
        insight for insight in insights if _can_review_insight(request.user, insight)
    ]
    context = base_context(request)
    context.update(
        {
            "review_conditions": review_conditions,
            "review_insights": review_insights,
            "review_count": len(review_conditions) + len(review_insights),
        }
    )
    return render(request, "iatrain/reviews/list.html", context)


@login_required
@require_POST
def condition_review(request, pk):
    require_coach(request)
    condition = get_object_or_404(
        AthleteCondition.objects.select_related("athlete_profile", "organization"), pk=pk
    )
    decision = request.POST.get("decision")
    if decision not in {"accept", "reject"}:
        raise PermissionDenied
    try:
        review_athlete_condition(
            user=request.user,
            condition=condition,
            accept=decision == "accept",
        )
    except (PermissionDenied, ValidationError) as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            "Condició confirmada." if decision == "accept" else "Condició descartada.",
        )
    return redirect(safe_next(request, "iatrain_profile_review"))


@login_required
@require_POST
def condition_resolve(request, pk):
    require_coach(request)
    condition = get_object_or_404(
        AthleteCondition.objects.select_related("athlete_profile", "organization"), pk=pk
    )
    try:
        resolve_athlete_condition(user=request.user, condition=condition)
    except (PermissionDenied, ValidationError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Condició resolta.")
    return redirect(safe_next(request, "iatrain_profile_review"))


@login_required
@require_POST
def insight_review(request, pk):
    require_coach(request)
    insight = get_object_or_404(
        AthleteInsight.objects.select_related("athlete_profile", "organization"), pk=pk
    )
    decision = request.POST.get("decision")
    if decision not in {"accept", "reject"}:
        raise PermissionDenied
    try:
        review_athlete_insight(
            user=request.user,
            insight=insight,
            accept=decision == "accept",
        )
    except (PermissionDenied, ValidationError) as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            "Interpretació confirmada."
            if decision == "accept"
            else "Interpretació descartada.",
        )
    return redirect(safe_next(request, "iatrain_profile_review"))
