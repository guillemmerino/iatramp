from .models import (
    BiomechanicalContext,
    ContextAngleConstraint,
    EvidenceReference,
    MuscleActionFunction,
    MuscleStabilizationFunction,
)


def merge_biomechanics_identity(*, canonical, duplicate):
    authored_models = (
        EvidenceReference,
        BiomechanicalContext,
        ContextAngleConstraint,
        MuscleActionFunction,
        MuscleStabilizationFunction,
    )
    for model in authored_models:
        model.objects.filter(authored_by=duplicate).update(authored_by=canonical)
    for model in (BiomechanicalContext, MuscleActionFunction, MuscleStabilizationFunction):
        model.objects.filter(last_validated_by=duplicate).update(last_validated_by=canonical)

