from dataclasses import dataclass

from django.db.models import Q

from iatrain_motion.models import EditorialStatus, MotionRelation

from .models import MuscleActionFunction, MuscleStabilizationFunction


@dataclass(frozen=True)
class ContractionInference:
    mode: str
    confidence: str
    explanation: str
    limitations: tuple[str, ...] = ()


def _actions_are_opposites(first, second, *, include_drafts=False):
    queryset = MotionRelation.objects.filter(
        relation_type=MotionRelation.RelationType.OPPOSITE_OF,
    ).filter(Q(source=first, target=second) | Q(source=second, target=first))
    if not include_drafts:
        queryset = queryset.filter(editorial_status=EditorialStatus.VALIDATED)
    return queryset.exists()


def infer_contraction_mode(
    *,
    function,
    phase_action,
    intent,
    muscle_is_targeted,
    include_drafts=False,
):
    """Infer an intended contraction without pretending that kinematics proves activation."""
    limitations = (
        "És una inferència funcional; la cinemàtica no confirma activació muscular real.",
        "Músculs biarticulars o canvis de braç de moment poden requerir un model més detallat.",
    )
    if not muscle_is_targeted:
        return ContractionInference(
            "indeterminate",
            "low",
            "No s'ha declarat que el múscul estigui actiu o sigui objectiu de la fase.",
            limitations,
        )
    if intent == "hold":
        return ContractionInference(
            "isometric",
            "moderate",
            "La fase demana tensió amb manteniment de la posició articular.",
            limitations,
        )
    if phase_action.pk == function.action_id and intent in {"produce", "assist"}:
        return ContractionInference(
            "concentric",
            "moderate",
            f"La fase produeix {phase_action.name}, acció a la qual contribueix {function.muscle.name}.",
            limitations,
        )
    if intent == "control" and _actions_are_opposites(
        function.action,
        phase_action,
        include_drafts=include_drafts,
    ):
        return ContractionInference(
            "eccentric",
            "moderate",
            f"La fase es mou cap a {phase_action.name} mentre {function.muscle.name} controla "
            f"l'acció oposada a {function.action.name}.",
            limitations,
        )
    return ContractionInference(
        "indeterminate",
        "low",
        "La funció, l'acció observada i la intenció no permeten classificar la contracció.",
        limitations,
    )


def build_biomechanics_context(*, action_codes=(), muscle_codes=(), include_drafts=False):
    statuses = (
        (EditorialStatus.DRAFT, EditorialStatus.VALIDATED)
        if include_drafts
        else (EditorialStatus.VALIDATED,)
    )
    action_functions = MuscleActionFunction.objects.filter(
        editorial_status__in=statuses,
    ).select_related("muscle", "action", "context").prefetch_related(
        "evidence_links__evidence"
    )
    stabilizations = MuscleStabilizationFunction.objects.filter(
        editorial_status__in=statuses,
    ).select_related("muscle", "target_joint", "target_segment", "context").prefetch_related(
        "evidence_links__evidence"
    )
    if action_codes:
        action_functions = action_functions.filter(action__code__in=action_codes)
    if muscle_codes:
        action_functions = action_functions.filter(muscle__code__in=muscle_codes)
        stabilizations = stabilizations.filter(muscle__code__in=muscle_codes)
    return {
        "muscle_action_functions": [
            {
                "code": row.code,
                "muscle": row.muscle.code,
                "action": row.action.code,
                "context": row.context.code if row.context_id else None,
                "contribution_class": row.contribution_class,
                "statement": row.statement,
                "conditions": row.conditions,
                "limitations": row.limitations,
                "editorial_status": row.editorial_status,
                "evidence": [link.evidence.code for link in row.evidence_links.all()],
            }
            for row in action_functions
        ],
        "stabilization_functions": [
            {
                "code": row.code,
                "muscle": row.muscle.code,
                "target": (row.target_joint or row.target_segment).code,
                "stabilization_type": row.stabilization_type,
                "context": row.context.code if row.context_id else None,
                "statement": row.statement,
                "conditions": row.conditions,
                "limitations": row.limitations,
                "editorial_status": row.editorial_status,
                "evidence": [link.evidence.code for link in row.evidence_links.all()],
            }
            for row in stabilizations
        ],
        "interpretation_policy": {
            "activation_is_observed": False,
            "contraction_requires_phase_intent": True,
            "only_validated_by_default": not include_drafts,
        },
    }
