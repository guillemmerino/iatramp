from django.db.models import Q

from iatrain_biomechanics.models import (
    MuscleActionFunction,
    MuscleStabilizationFunction,
)
from iatrain_motion.models import EditorialStatus, MotionConcept

from .models import ExercisePhaseAction, ExercisePhaseMuscleRole


def _validated_roles():
    return ExercisePhaseMuscleRole.objects.filter(
        phase__revision__editorial_status=EditorialStatus.VALIDATED
    )


def motion_dependency_issues(*, instance, target_status):
    if target_status == EditorialStatus.VALIDATED or not isinstance(instance, MotionConcept):
        return []
    action_count = ExercisePhaseAction.objects.filter(
        action=instance,
        phase__revision__editorial_status=EditorialStatus.VALIDATED,
    ).count()
    muscle_count = _validated_roles().filter(muscle=instance).count()
    if action_count or muscle_count:
        return [
            f"el concepte sosté {action_count} accions de fase i {muscle_count} rols musculars "
            "d'exercicis validats"
        ]
    return []


def biomechanics_dependency_issues(*, instance, target_status):
    if target_status == EditorialStatus.VALIDATED:
        return []
    roles = _validated_roles()
    if isinstance(instance, MuscleActionFunction):
        count = roles.filter(action_function=instance).count()
    elif isinstance(instance, MuscleStabilizationFunction):
        count = roles.filter(stabilization_function=instance).count()
    else:
        count = 0
    return [f"la funció sosté {count} rols musculars d'exercicis validats"] if count else []
