from iatrain_motion.models import EditorialStatus

from .models import ExerciseRevision


def build_exercise_context(
    *,
    owner,
    action_codes=(),
    muscle_codes=(),
    objective_codes=(),
    include_drafts=False,
):
    """Build a tenant-scoped, explainable read projection for a suggestion engine."""
    statuses = (
        (EditorialStatus.DRAFT, EditorialStatus.VALIDATED)
        if include_drafts
        else (EditorialStatus.VALIDATED,)
    )
    queryset = ExerciseRevision.objects.filter(
        exercise__catalog__owner=owner,
        exercise__catalog__is_active=True,
        exercise__is_active=True,
        exercise__kind="variant",
        editorial_status__in=statuses,
    ).select_related("exercise", "exercise__parent", "exercise__catalog").prefetch_related(
        "objectives",
        "equipment_requirements__equipment",
        "constraints",
        "phases__actions__action",
        "phases__muscle_roles__muscle",
        "phases__muscle_roles__action_function",
        "phases__muscle_roles__stabilization_function",
    )
    if action_codes:
        queryset = queryset.filter(phases__actions__action__code__in=action_codes)
    if muscle_codes:
        queryset = queryset.filter(phases__muscle_roles__muscle__code__in=muscle_codes)
    if objective_codes:
        queryset = queryset.filter(objectives__objective__in=objective_codes)
    queryset = queryset.distinct()

    exercises = []
    for revision in queryset:
        phases = []
        explanation_paths = []
        for phase in revision.phases.all():
            actions = [
                {
                    "code": link.action.code,
                    "role": link.role,
                    "intent": phase.intent,
                    "verification_state": link.verification_state,
                    "rationale": link.rationale,
                }
                for link in phase.actions.all()
            ]
            muscles = []
            for role in phase.muscle_roles.all():
                basis = role.action_function or role.stabilization_function
                basis_type = "action_function" if role.action_function_id else "stabilization_function"
                muscles.append(
                    {
                        "code": role.muscle.code,
                        "role": role.role,
                        "expected_contraction": role.expected_contraction,
                        "basis_type": basis_type,
                        "basis_code": basis.code,
                        "verification_state": role.verification_state,
                        "rationale": role.rationale,
                    }
                )
                explanation_paths.append(
                    {
                        "exercise": revision.exercise.code,
                        "phase": phase.code,
                        "intent": phase.intent,
                        "muscle": role.muscle.code,
                        "biomechanical_basis": basis.code,
                        "expected_contraction": role.expected_contraction,
                    }
                )
            phases.append(
                {
                    "code": phase.code,
                    "name": phase.name,
                    "sequence_index": phase.sequence_index,
                    "intent": phase.intent,
                    "is_key_phase": phase.is_key_phase,
                    "actions": actions,
                    "muscles": muscles,
                }
            )
        exercises.append(
            {
                "code": revision.exercise.code,
                "name": revision.exercise.name,
                "family": revision.exercise.parent.code,
                "revision": revision.revision_number,
                "editorial_status": revision.editorial_status,
                "modality": revision.modality,
                "movement_pattern": revision.movement_pattern,
                "difficulty": revision.difficulty,
                "laterality": revision.laterality,
                "kinetic_chain": revision.kinetic_chain,
                "description": revision.description,
                "objectives": [row.objective for row in revision.objectives.all()],
                "equipment": [
                    {
                        "code": row.equipment.code,
                        "requirement": row.requirement,
                    }
                    for row in revision.equipment_requirements.all()
                ],
                "constraints": [
                    {
                        "code": row.code,
                        "kind": row.kind,
                        "severity": row.severity,
                        "statement": row.statement,
                    }
                    for row in revision.constraints.all()
                ],
                "phases": phases,
                "explanation_paths": explanation_paths,
            }
        )
    return {
        "owner_id": owner.pk,
        "exercises": exercises,
        "policy": {
            "catalog_scope": "personal_only",
            "only_validated_by_default": not include_drafts,
            "muscle_activation_is_inferred": True,
            "prescription_is_separate": True,
        },
    }
