from .models import (
    CanonicalJoint,
    CanonicalLandmark,
    CanonicalSegment,
    JointAngleDefinition,
    MotionConcept,
    MotionRelation,
    SkeletonSchema,
)


def merge_motion_identity(*, canonical, duplicate):
    """Retarget anatomical authorship before Core removes a duplicate identity."""
    authored_models = (
        MotionConcept,
        MotionRelation,
        SkeletonSchema,
        CanonicalLandmark,
        CanonicalSegment,
        CanonicalJoint,
        JointAngleDefinition,
    )
    for model in authored_models:
        model.objects.filter(authored_by=duplicate).update(authored_by=canonical)
    for model in (MotionConcept, MotionRelation, SkeletonSchema):
        model.objects.filter(last_validated_by=duplicate).update(last_validated_by=canonical)
