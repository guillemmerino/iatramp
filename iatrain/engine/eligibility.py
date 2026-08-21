"""Minimal server-side preflight for explicit participant stop conditions."""

from dataclasses import dataclass, replace


EXCLUDE_FROM_BLOCK = "exclude_from_block"
ALLOW_AGENT_INTERPRETATION = "allow_agent_interpretation"
# Kept for compatibility with historical decision payloads. Missing age is now
# context for the planning agent, not a mandatory deterministic interruption.
CONTINUE_CONSERVATIVELY = "continue_conservatively"


@dataclass(frozen=True, slots=True)
class EligibilityReview:
    active_participant_plan_ids: tuple[int, ...]
    excluded_participant_plan_ids: tuple[int, ...]
    exclusion_reasons: dict[int, str]
    issues: tuple[dict, ...]

    @property
    def needs_decision(self):
        return bool(self.issues)

    def payload(self):
        return {
            "version": "1.0",
            "kind": "participant_eligibility",
            "issues": list(self.issues),
            "active_participant_plan_ids": list(self.active_participant_plan_ids),
            "excluded_participant_plan_ids": list(self.excluded_participant_plan_ids),
        }


def analyze_participant_eligibility(*, context, decisions=None):
    """Return unresolved coach decisions without delegating safety to the LLM."""

    decisions = {str(key): value for key, value in (decisions or {}).items()}
    active = []
    excluded = []
    exclusion_reasons = {}
    issues = []

    for athlete in context.athletes:
        participant_id = athlete.participant_plan_id
        decision = decisions.get(str(participant_id), "")
        conditions = athlete.payload.get("active_conditions", [])
        if decision == EXCLUDE_FROM_BLOCK:
            excluded.append(participant_id)
            exclusion_reasons[participant_id] = (
                "Exclusió d’aquest bloc confirmada per l’entrenador."
            )
            continue
        uncertain_conditions = [
            condition
            for condition in conditions
            if condition.get("training_impact") in {"avoid", "modify"}
            and condition.get("applicability_scope", "unknown") == "unknown"
            and not (condition.get("body_region") or {}).get("code")
        ]
        uncertain_exclusion = next(
            (
                condition
                for condition in uncertain_conditions
                if decisions.get(f"condition_{condition.get('id')}")
                == EXCLUDE_FROM_BLOCK
            ),
            None,
        )
        if uncertain_exclusion:
            excluded.append(participant_id)
            exclusion_reasons[participant_id] = (
                "Exclusió confirmada per l'entrenador davant una condició amb "
                "abast pendent: "
                + uncertain_exclusion.get("title", "condició activa")
            )
            continue
        stop_conditions = [
            condition
            for condition in conditions
            if condition.get("training_impact") == "stop"
        ]
        if stop_conditions:
            issues.append(
                {
                    "participant_plan_id": participant_id,
                    "reason_code": "active_training_stop",
                    "title": "Indicació activa de no entrenar",
                    "explanation": (
                        "Aquesta gimnasta no pot rebre una variant física mentre "
                        "l'estat continuï marcat com a «No entrenar»."
                    ),
                    "choices": [
                        {
                            "value": EXCLUDE_FROM_BLOCK,
                            "label": "Excloure-la només d'aquest bloc",
                        }
                    ],
                    "profile_review_available": True,
                }
            )
            continue

        for condition in uncertain_conditions:
            decision_key = f"condition_{condition.get('id')}"
            if decisions.get(decision_key) == ALLOW_AGENT_INTERPRETATION:
                condition["coach_scope_decision"] = ALLOW_AGENT_INTERPRETATION
                continue
            issues.append(
                {
                    "participant_plan_id": participant_id,
                    "decision_key": decision_key,
                    "reason_code": "condition_scope_unknown",
                    "title": "Falta concretar l’abast d’una condició",
                    "explanation": (
                        f"«{condition.get('title', 'Condició activa')}» està marcada com "
                        "a condició que obliga a evitar o modificar, però no indica una "
                        "regió corporal ni un abast global."
                    ),
                    "choices": [
                        {
                            "value": ALLOW_AGENT_INTERPRETATION,
                            "label": "Deixar que l’agent busqui adaptacions prudents",
                        },
                        {
                            "value": EXCLUDE_FROM_BLOCK,
                            "label": "Excloure-la només d’aquest bloc",
                        },
                    ],
                    "profile_review_available": True,
                }
            )

        active.append(participant_id)

    return EligibilityReview(
        active_participant_plan_ids=tuple(active),
        excluded_participant_plan_ids=tuple(excluded),
        exclusion_reasons=exclusion_reasons,
        issues=tuple(issues),
    )


def request_after_eligibility(request, review):
    return replace(
        request,
        participant_plan_ids=review.active_participant_plan_ids,
        excluded_participant_plan_ids=review.excluded_participant_plan_ids,
        contract_version="3.0",
    )
