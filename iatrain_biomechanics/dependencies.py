from django.db.models import Q

from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation

from .models import MuscleActionFunction, MuscleStabilizationFunction


def motion_dependency_issues(*, instance, target_status):
    if target_status == EditorialStatus.VALIDATED:
        return []
    issues = []
    if isinstance(instance, MotionConcept):
        action_count = MuscleActionFunction.objects.filter(
            Q(muscle=instance) | Q(action=instance),
            editorial_status=EditorialStatus.VALIDATED,
        ).count()
        stabilization_count = MuscleStabilizationFunction.objects.filter(
            Q(muscle=instance) | Q(target_joint=instance) | Q(target_segment=instance),
            editorial_status=EditorialStatus.VALIDATED,
        ).count()
        if action_count or stabilization_count:
            issues.append(
                f"el concepte sosté {action_count} funcions d'acció i "
                f"{stabilization_count} funcions estabilitzadores validades"
            )
    elif isinstance(instance, MotionRelation):
        if instance.relation_type == MotionRelation.RelationType.ACTION_AT_JOINT:
            count = MuscleActionFunction.objects.filter(
                action=instance.source,
                editorial_status=EditorialStatus.VALIDATED,
            ).count()
            if count:
                issues.append(f"la relació localitza l'acció de {count} funcions validades")
        elif instance.relation_type == MotionRelation.RelationType.SPANS_JOINT:
            action_count = MuscleActionFunction.objects.filter(
                muscle=instance.source,
                action__outgoing_motion_relations__target=instance.target,
                action__outgoing_motion_relations__relation_type=(
                    MotionRelation.RelationType.ACTION_AT_JOINT
                ),
                editorial_status=EditorialStatus.VALIDATED,
            ).distinct().count()
            stabilization_count = MuscleStabilizationFunction.objects.filter(
                muscle=instance.source,
                target_joint=instance.target,
                editorial_status=EditorialStatus.VALIDATED,
            ).count()
            if action_count or stabilization_count:
                issues.append(
                    f"la relació sosté {action_count} funcions d'acció i "
                    f"{stabilization_count} estabilitzacions validades"
                )
        elif instance.relation_type == MotionRelation.RelationType.MEMBER_OF_MUSCLE_GROUP:
            count = (
                MuscleActionFunction.objects.filter(
                    muscle=instance.source,
                    editorial_status=EditorialStatus.VALIDATED,
                ).count()
                + MuscleStabilizationFunction.objects.filter(
                    muscle=instance.source,
                    editorial_status=EditorialStatus.VALIDATED,
                ).count()
            )
            other_validated_memberships = MotionRelation.objects.filter(
                source=instance.source,
                relation_type=MotionRelation.RelationType.MEMBER_OF_MUSCLE_GROUP,
                editorial_status=EditorialStatus.VALIDATED,
            ).exclude(pk=instance.pk)
            if count and not other_validated_memberships.exists():
                issues.append(
                    f"és l'única pertinença de grup per a un múscul amb {count} funcions validades"
                )
    return issues
