from dataclasses import dataclass

from iatrain_motion.models import EditorialStatus, MotionConcept, MotionRelation

from iatrain_biomechanics.reasoning import infer_contraction_mode

from .models import (
    ExerciseEquipmentRequirement,
    ExercisePhase,
    ExercisePhaseMuscleRole,
    ExerciseRevision,
)


COMPLETENESS_SCHEMA_VERSION = "exercise_completeness_v1"


@dataclass(frozen=True)
class CompletenessIssue:
    code: str
    field_path: str
    description: str
    severity: str = "required"


def evaluate_revision(revision, *, require_validated_dependencies=False):
    issues = []

    def required(code, path, description):
        issues.append(CompletenessIssue(code, path, description, "required"))

    if not revision.description.strip():
        required("missing_description", "revision.description", "Falta la descripció funcional.")
    if not revision.setup.strip():
        required("missing_setup", "revision.setup", "Falta la posició o preparació inicial.")
    if not revision.execution.strip():
        required("missing_execution", "revision.execution", "Falta la seqüència d'execució.")
    if not revision.coaching_cues.strip():
        required("missing_cues", "revision.coaching_cues", "Falten indicacions observables.")
    if not revision.objectives.exists():
        required("missing_objective", "revision.objectives", "Falta almenys un objectiu.")
    elif not revision.objectives.filter(priority="primary").exists():
        required(
            "missing_primary_objective",
            "revision.objectives",
            "Falta indicar quin objectiu és principal.",
        )
    required_equipment = revision.equipment_requirements.filter(
        requirement=ExerciseEquipmentRequirement.Requirement.REQUIRED
    )
    if revision.requires_equipment and not required_equipment.exists():
        required(
            "missing_required_equipment",
            "revision.equipment_requirements",
            "S'ha declarat material necessari però no s'ha especificat.",
        )
    if not revision.requires_equipment and required_equipment.exists():
        required(
            "unexpected_required_equipment",
            "revision.requires_equipment",
            "Hi ha material necessari però la revisió diu que no en requereix.",
        )

    key_phases = revision.phases.filter(is_key_phase=True)
    if not key_phases.exists():
        required("missing_key_phase", "revision.phases", "Falta almenys una fase clau.")
    for phase in revision.phases.all():
        if phase.is_key_phase and not phase.actions.exists() and not phase.muscle_roles.exists():
            required(
                f"empty_key_phase_{phase.code}",
                f"phases.{phase.code}",
                f"La fase clau {phase.name} no té accions ni rols musculars.",
            )
        if phase.intent in {
            ExercisePhase.Intent.PRODUCE,
            ExercisePhase.Intent.ASSIST,
            ExercisePhase.Intent.CONTROL,
        } and not phase.actions.exists():
            required(
                f"missing_phase_action_{phase.code}",
                f"phases.{phase.code}.actions",
                f"La fase {phase.name} necessita una acció cinemàtica.",
            )

    for action_link in revision.phases.all().prefetch_related("actions"):
        for link in action_link.actions.all():
            if link.action.kind != MotionConcept.Kind.JOINT_ACTION:
                required(
                    f"invalid_action_kind_{link.pk}",
                    f"phases.{action_link.code}.actions",
                    "Una connexió de fase no apunta a una acció articular.",
                )
            if require_validated_dependencies and link.action.editorial_status != EditorialStatus.VALIDATED:
                required(
                    f"unvalidated_action_{link.action.code}",
                    f"phases.{action_link.code}.actions.{link.action.code}",
                    f"L'acció {link.action.name} encara no està validada.",
                )
            if link.verification_state == link.VerificationState.PENDING:
                required(
                    f"pending_phase_action_{link.pk}",
                    f"phases.{action_link.code}.actions.{link.action.code}",
                    "La connexió cinemàtica continua pendent de confirmació editorial.",
                )

    roles = ExercisePhaseMuscleRole.objects.filter(
        phase__revision=revision
    ).select_related("phase", "muscle", "action_function", "stabilization_function")
    for role in roles:
        basis = role.action_function or role.stabilization_function
        if basis is None:
            required(
                f"missing_biomechanical_basis_{role.pk}",
                f"phases.{role.phase.code}.muscles.{role.muscle.code}",
                "El rol muscular no té una base biomecànica.",
            )
            continue
        if role.verification_state == ExercisePhaseMuscleRole.VerificationState.PENDING:
            required(
                f"pending_muscle_role_{role.pk}",
                f"phases.{role.phase.code}.muscles.{role.muscle.code}",
                "El rol muscular continua pendent de confirmació editorial.",
            )
        if role.action_function_id:
            phase_actions = list(role.phase.actions.select_related("action"))
            inferred = None
            for phase_action in phase_actions:
                candidate = infer_contraction_mode(
                    function=role.action_function,
                    phase_action=phase_action.action,
                    intent=role.phase.intent,
                    muscle_is_targeted=True,
                    include_drafts=not require_validated_dependencies,
                )
                if candidate.mode != "indeterminate":
                    inferred = candidate
                    break
            if role.phase.intent == ExercisePhase.Intent.HOLD:
                inferred_mode = "isometric"
            elif inferred is None:
                inferred_mode = "indeterminate"
                required(
                    f"incompatible_muscle_basis_{role.pk}",
                    f"phases.{role.phase.code}.muscles.{role.muscle.code}.basis",
                    "La funció biomecànica no és compatible amb l'acció i la intenció de la fase.",
                )
            else:
                inferred_mode = inferred.mode
            if (
                inferred_mode != "indeterminate"
                and role.expected_contraction
                not in {inferred_mode, ExercisePhaseMuscleRole.ExpectedContraction.VARIABLE}
            ):
                required(
                    f"inconsistent_contraction_{role.pk}",
                    f"phases.{role.phase.code}.muscles.{role.muscle.code}.expected_contraction",
                    f"La contracció declarada no concorda amb la inferència {inferred_mode}.",
                )
        if require_validated_dependencies:
            if role.muscle.editorial_status != EditorialStatus.VALIDATED:
                required(
                    f"unvalidated_muscle_{role.muscle.code}",
                    f"phases.{role.phase.code}.muscles.{role.muscle.code}",
                    f"El múscul {role.muscle.name} encara no està validat.",
                )
            if basis.editorial_status != EditorialStatus.VALIDATED:
                required(
                    f"unvalidated_basis_{basis.code}",
                    f"phases.{role.phase.code}.muscles.{role.muscle.code}.basis",
                    f"La funció biomecànica {basis.code} encara no està validada.",
                )

    return issues


def audit_exercise_catalog(*, catalog=None, include_drafts=False):
    revisions = ExerciseRevision.objects.exclude(editorial_status=EditorialStatus.RETIRED)
    if catalog is not None:
        revisions = revisions.filter(exercise__catalog=catalog)
    if not include_drafts:
        revisions = revisions.filter(editorial_status=EditorialStatus.VALIDATED)
    issues = []
    for revision in revisions.prefetch_related(
        "objectives", "equipment_requirements", "phases__actions", "phases__muscle_roles"
    ):
        issues.extend(
            f"{revision.exercise.code}@{revision.revision_number}: {issue.description}"
            for issue in evaluate_revision(
                revision,
                require_validated_dependencies=not include_drafts,
            )
        )
    return issues
