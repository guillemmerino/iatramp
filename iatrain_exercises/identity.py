from .models import (
    Exercise,
    ExerciseCatalog,
    ExerciseChangeProposal,
    ExercisePhase,
    ExerciseRevision,
)


def merge_exercises_identity(*, canonical, duplicate):
    """Retarget private catalogs and authorship during the core identity merge."""
    for catalog in ExerciseCatalog.objects.filter(owner=duplicate).order_by("id"):
        base_code = catalog.code
        base_name = catalog.name
        suffix = f"merged_{duplicate.pk}_{catalog.pk}"
        if ExerciseCatalog.objects.filter(owner=canonical, code=catalog.code).exists():
            catalog.code = f"{base_code}_{suffix}"
        if ExerciseCatalog.objects.filter(owner=canonical, name__iexact=catalog.name).exists():
            catalog.name = f"{base_name} ({suffix})"
        catalog.owner = canonical
        catalog.save()
    Exercise.objects.filter(created_by=duplicate).update(created_by=canonical)
    ExerciseRevision.objects.filter(authored_by=duplicate).update(authored_by=canonical)
    ExerciseRevision.objects.filter(last_validated_by=duplicate).update(
        last_validated_by=canonical
    )
    ExercisePhase.objects.filter(authored_by=duplicate).update(authored_by=canonical)
    ExerciseChangeProposal.objects.filter(created_by=duplicate).update(created_by=canonical)
    ExerciseChangeProposal.objects.filter(reviewed_by=duplicate).update(reviewed_by=canonical)
