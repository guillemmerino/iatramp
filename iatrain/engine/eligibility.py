"""Deterministic preflight decisions for participant-level block safety."""

from dataclasses import dataclass, replace


EXCLUDE_FROM_BLOCK = "exclude_from_block"
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
        stop_conditions = [
            condition
            for condition in conditions
            if condition.get("training_impact") == "stop"
        ]
        if stop_conditions:
            if decision == EXCLUDE_FROM_BLOCK:
                excluded.append(participant_id)
                titles = [
                    condition.get("title", "indicació activa de no entrenar")
                    for condition in stop_conditions
                ]
                exclusion_reasons[participant_id] = (
                    "Exclusió confirmada per l'entrenador: " + ", ".join(titles)
                )
                continue
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

        age_years = athlete.payload.get("athlete", {}).get("age_years")
        if age_years is None and decision != CONTINUE_CONSERVATIVELY:
            issues.append(
                {
                    "participant_plan_id": participant_id,
                    "reason_code": "missing_age",
                    "title": "Falta l'edat o la data de naixement",
                    "explanation": (
                        "Es pot continuar amb la dosificació més conservadora o "
                        "completar el perfil abans de generar."
                    ),
                    "choices": [
                        {
                            "value": CONTINUE_CONSERVATIVELY,
                            "label": "Continuar amb criteri conservador",
                        }
                    ],
                    "profile_review_available": True,
                }
            )
            continue

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
        contract_version="2.0",
    )
