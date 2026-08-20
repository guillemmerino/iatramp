from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Person
from iatrain.models import KnowledgeEditorialEvent
from iatrain_motion.models import EditorialStatus

from .checks import evaluate_revision
from .models import ExerciseRevision


ALLOWED_TRANSITIONS = {
    EditorialStatus.DRAFT: {EditorialStatus.VALIDATED, EditorialStatus.RETIRED},
    EditorialStatus.VALIDATED: {EditorialStatus.RETIRED},
    EditorialStatus.RETIRED: {EditorialStatus.DRAFT},
}


@dataclass(frozen=True)
class EditorialTransition:
    instance: ExerciseRevision
    previous_status: str


def _editor_for_user(user, revision):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Cal iniciar sessió per governar el catàleg.")
    try:
        editor = user.person
    except Person.DoesNotExist as exc:
        raise ValidationError("L'editor necessita una identitat.") from exc
    if not editor.is_active:
        raise ValidationError("L'editor necessita una identitat activa.")
    if editor.pk != revision.exercise.catalog.owner_id and not user.is_superuser:
        raise PermissionDenied("Només el propietari pot governar aquest catàleg privat.")
    return editor


@transaction.atomic
def transition_exercise_revision(*, user, revision, target_status, reason=""):
    revision = ExerciseRevision.objects.select_for_update().select_related(
        "exercise__catalog"
    ).get(pk=revision.pk)
    editor = _editor_for_user(user, revision)
    previous_status = revision.editorial_status
    if target_status not in ALLOWED_TRANSITIONS:
        raise ValidationError("Estat editorial desconegut.")
    if target_status == previous_status:
        return EditorialTransition(revision, previous_status)
    if target_status not in ALLOWED_TRANSITIONS[previous_status]:
        raise ValidationError(f"Transició editorial no permesa: {previous_status} → {target_status}.")
    if target_status == EditorialStatus.VALIDATED:
        issues = evaluate_revision(revision, require_validated_dependencies=True)
        if issues:
            raise ValidationError(
                "La revisió no és validable:\n- " + "\n- ".join(issue.description for issue in issues)
            )
        revision.last_validated_by = editor
        revision.last_validated_at = timezone.now()
    revision.editorial_status = target_status
    revision.full_clean()
    revision.save(
        update_fields=(
            "editorial_status", "last_validated_by", "last_validated_at", "updated_at"
        )
    )
    KnowledgeEditorialEvent.objects.create(
        target_model=revision._meta.label_lower,
        target_id=revision.pk,
        target_repr=str(revision),
        from_status=previous_status,
        to_status=target_status,
        decided_by=editor,
        reason=str(reason or "").strip(),
        snapshot={
            "exercise_id": revision.exercise_id,
            "revision_number": revision.revision_number,
            "movement_pattern": revision.movement_pattern,
            "modality": revision.modality,
            "phase_ids": list(revision.phases.values_list("id", flat=True)),
            "objective_ids": list(revision.objectives.values_list("id", flat=True)),
            "provenance": revision.provenance,
        },
    )
    return EditorialTransition(revision, previous_status)
