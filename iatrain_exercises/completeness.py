from django.db import transaction

from .checks import COMPLETENESS_SCHEMA_VERSION, evaluate_revision
from .models import ExerciseGap


@transaction.atomic
def refresh_revision_gaps(revision):
    """Synchronize deterministic gaps without overwriting human or LLM decisions."""
    detected = {
        issue.code: issue
        for issue in evaluate_revision(revision, require_validated_dependencies=False)
    }
    existing = {
        gap.requirement_code: gap
        for gap in revision.gaps.select_for_update().filter(
            schema_version=COMPLETENESS_SCHEMA_VERSION,
            detected_by=ExerciseGap.DetectedBy.SYSTEM,
        )
    }
    for code, issue in detected.items():
        gap = existing.get(code)
        if gap is None:
            ExerciseGap.objects.create(
                revision=revision,
                requirement_code=code,
                field_path=issue.field_path,
                severity=issue.severity,
                detected_by=ExerciseGap.DetectedBy.SYSTEM,
                description=issue.description,
                schema_version=COMPLETENESS_SCHEMA_VERSION,
            )
        elif gap.status in {ExerciseGap.Status.RESOLVED, ExerciseGap.Status.DISMISSED}:
            gap.status = ExerciseGap.Status.OPEN
            gap.resolution_notes = "El validador ha tornat a detectar el buit."
            gap.save(update_fields=("status", "resolution_notes", "updated_at"))
    for code, gap in existing.items():
        if code not in detected and gap.status in {ExerciseGap.Status.OPEN, ExerciseGap.Status.PROPOSED}:
            gap.status = ExerciseGap.Status.RESOLVED
            gap.resolution_notes = "Resolt en tornar a executar l'esquema de completesa."
            gap.save(update_fields=("status", "resolution_notes", "updated_at"))
    return list(revision.gaps.filter(status__in=(ExerciseGap.Status.OPEN, ExerciseGap.Status.PROPOSED)))
