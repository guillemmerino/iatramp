"""Validation rules for block generation contracts."""

from decimal import Decimal

from django.core.exceptions import ValidationError

from iatrain.models import (
    GymEquipment,
    PhysicalExercisePrescription,
    SessionItemAlternative,
    TrainingBlock,
    TrainingSessionItem,
    TrainingSessionRevision,
)
from iatrain_exercises.models import ExerciseRevision
from iatrain_exercises.models import ExerciseObjective

from .contracts import (
    AthleteAdjustmentProposal,
    BlockCoverage,
    BlockGenerationProposal,
    BlockGenerationRequest,
    BlockItemProposal,
    BlockLoadEstimate,
    BlockObjective,
    ExerciseAlternativeProposal,
    ExerciseDoseProposal,
    PHYSICAL_BLOCK_HARD_CONSTRAINTS,
    TARGET_INTENSITIES,
)


def _add(errors, path, message):
    errors.setdefault(path, []).append(message)


def _normalized(values):
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def _validate_unique_positive_ids(errors, path, values, *, required=False):
    if required and not values:
        _add(errors, path, "Cal indicar almenys un identificador.")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in values):
        _add(errors, path, "Tots els identificadors han de ser enters positius.")
    if len(values) != len(set(values)):
        _add(errors, path, "No es poden repetir identificadors.")


def validate_block_generation_request(request, *, revision=None):
    if not isinstance(request, BlockGenerationRequest):
        raise ValidationError("La petició no compleix el contracte BlockGenerationRequest.")
    errors = {}
    if request.contract_version != "1.0":
        _add(errors, "contract_version", "La versió del contracte no està suportada.")
    if not isinstance(request.session_revision_id, int) or request.session_revision_id < 1:
        _add(errors, "session_revision_id", "Cal una versió de sessió vàlida.")
    if not isinstance(request.sequence_index, int) or request.sequence_index < 1:
        _add(errors, "sequence_index", "La posició ha de ser un enter positiu.")
    if not isinstance(request.name, str) or not request.name.strip():
        _add(errors, "name", "El bloc necessita un nom.")
    elif len(request.name) > 160:
        _add(errors, "name", "El nom del bloc no pot superar 160 caràcters.")
    if request.block_role not in TrainingBlock.Role.values:
        _add(errors, "block_role", "La funció del bloc no és vàlida.")
    if request.domain != TrainingBlock.Domain.PHYSICAL:
        _add(errors, "domain", "Aquest contracte només admet generació física.")
    if request.execution_mode not in TrainingBlock.ExecutionMode.values:
        _add(errors, "execution_mode", "El mode d'execució no és vàlid.")
    if not isinstance(request.planned_duration_minutes, int) or request.planned_duration_minutes < 1:
        _add(errors, "planned_duration_minutes", "La durada ha de ser positiva.")
    if not isinstance(request.objective, BlockObjective):
        _add(errors, "objective", "L'objectiu no compleix el contracte BlockObjective.")
    else:
        if not isinstance(request.objective.description, str) or not request.objective.description.strip():
            _add(errors, "objective.description", "Cal descriure l'objectiu del bloc.")
        if not isinstance(request.objective.primary_quality, str) or not request.objective.primary_quality.strip():
            _add(errors, "objective.primary_quality", "Cal una qualitat física principal.")
        elif request.objective.primary_quality not in ExerciseObjective.Objective.values:
            _add(errors, "objective.primary_quality", "La qualitat física principal no és vàlida.")
        invalid_secondary = set(request.objective.secondary_qualities) - set(
            ExerciseObjective.Objective.values
        )
        if invalid_secondary:
            _add(errors, "objective.secondary_qualities", "Hi ha qualitats secundàries no vàlides.")
        invalid_patterns = set(request.objective.movement_patterns) - set(
            ExerciseRevision.MovementPattern.values
        )
        if invalid_patterns:
            _add(errors, "objective.movement_patterns", "Hi ha patrons de moviment no vàlids.")
    if request.target_intensity not in TARGET_INTENSITIES:
        _add(errors, "target_intensity", "La intensitat objectiu no és vàlida.")
    if not isinstance(request.rounds, int) or request.rounds < 1:
        _add(errors, "rounds", "El nombre de rondes ha de ser positiu.")
    if (
        not isinstance(request.rest_between_rounds_seconds, int)
        or request.rest_between_rounds_seconds < 0
    ):
        _add(errors, "rest_between_rounds_seconds", "El descans no pot ser negatiu.")
    _validate_unique_positive_ids(
        errors, "participant_plan_ids", request.participant_plan_ids, required=True
    )
    _validate_unique_positive_ids(
        errors, "available_equipment_ids", request.available_equipment_ids
    )
    if len(request.hard_constraints) != len(_normalized(request.hard_constraints)):
        _add(errors, "hard_constraints", "Les restriccions han de ser úniques i no buides.")
    if set(request.hard_constraints) - set(PHYSICAL_BLOCK_HARD_CONSTRAINTS):
        _add(errors, "hard_constraints", "Hi ha restriccions obligatòries no suportades.")
    if len(request.preferences) != len(_normalized(request.preferences)):
        _add(errors, "preferences", "Les preferències han de ser úniques i no buides.")

    if revision is not None:
        if not isinstance(revision, TrainingSessionRevision):
            _add(errors, "session_revision_id", "La versió de sessió no és vàlida.")
        else:
            if revision.pk != request.session_revision_id:
                _add(errors, "session_revision_id", "La petició pertany a una altra versió.")
            if revision.status != TrainingSessionRevision.Status.DRAFT:
                _add(errors, "session_revision_id", "Només es pot generar sobre un esborrany.")
            expected_participants = set(
                revision.participant_plans.values_list("pk", flat=True)
            )
            if set(request.participant_plan_ids) != expected_participants:
                _add(
                    errors,
                    "participant_plan_ids",
                    "El bloc ha d'incloure tots els participants de la versió.",
                )
            if revision.blocks.filter(sequence_index=request.sequence_index).exists():
                _add(errors, "sequence_index", "Ja existeix un bloc en aquesta posició.")
            current_minutes = sum(
                revision.blocks.values_list("planned_duration_minutes", flat=True)
            )
            if current_minutes + request.planned_duration_minutes > revision.planned_duration_minutes:
                _add(
                    errors,
                    "planned_duration_minutes",
                    "El bloc faria superar la durada planificada de la sessió.",
                )
            equipment_ids = set(request.available_equipment_ids)
            if equipment_ids:
                if not revision.session.gym_id:
                    _add(
                        errors,
                        "available_equipment_ids",
                        "La sessió no té cap gimnàs assignat.",
                    )
                else:
                    available = set(
                        GymEquipment.objects.filter(
                            pk__in=equipment_ids,
                            gym_id=revision.session.gym_id,
                        )
                        .exclude(availability=GymEquipment.Availability.UNAVAILABLE)
                        .values_list("pk", flat=True)
                    )
                    if available != equipment_ids:
                        _add(
                            errors,
                            "available_equipment_ids",
                            "Hi ha material inexistent, no disponible o d'un altre gimnàs.",
                        )
    if errors:
        raise ValidationError(errors)
    return request


def _validate_dose(errors, path, dose: ExerciseDoseProposal):
    if not isinstance(dose, ExerciseDoseProposal):
        _add(errors, path, "La dosi no compleix el contracte ExerciseDoseProposal.")
        return
    if not isinstance(dose.exercise_revision_id, int) or dose.exercise_revision_id < 1:
        _add(errors, f"{path}.exercise_revision_id", "Cal una revisió d'exercici vàlida.")
    if dose.dose_mode not in PhysicalExercisePrescription.DoseMode.values:
        _add(errors, f"{path}.dose_mode", "El mode de dosificació no és vàlid.")
    if not isinstance(dose.sets, int) or dose.sets < 1:
        _add(errors, f"{path}.sets", "Les sèries han de ser positives.")
    required = {
        PhysicalExercisePrescription.DoseMode.REPETITIONS: ("repetitions", dose.repetitions),
        PhysicalExercisePrescription.DoseMode.DURATION: ("duration_seconds", dose.duration_seconds),
        PhysicalExercisePrescription.DoseMode.HOLD: ("duration_seconds", dose.duration_seconds),
        PhysicalExercisePrescription.DoseMode.DISTANCE: ("distance", dose.distance),
    }.get(dose.dose_mode)
    if required and required[1] is None:
        _add(errors, f"{path}.{required[0]}", "La dosi necessita aquest valor.")
    for field_name in ("repetitions", "duration_seconds"):
        value = getattr(dose, field_name)
        if value is not None and (not isinstance(value, int) or value < 1):
            _add(errors, f"{path}.{field_name}", "El valor ha de ser un enter positiu.")
    for field_name in (
        "tempo_eccentric_seconds",
        "tempo_pause_seconds",
        "tempo_concentric_seconds",
    ):
        value = getattr(dose, field_name)
        if value is not None and (not isinstance(value, int) or value < 0):
            _add(errors, f"{path}.{field_name}", "El tempo no pot ser negatiu.")
    if dose.distance is not None and dose.distance <= 0:
        _add(errors, f"{path}.distance", "La distància ha de ser positiva.")
    if dose.dose_mode == PhysicalExercisePrescription.DoseMode.DISTANCE and not dose.distance_unit:
        _add(errors, f"{path}.distance_unit", "La distància necessita una unitat.")
    if dose.distance_unit and dose.distance_unit not in PhysicalExercisePrescription.DistanceUnit.values:
        _add(errors, f"{path}.distance_unit", "La unitat de distància no és vàlida.")
    if (dose.load_value is None) != (not dose.load_unit):
        _add(errors, f"{path}.load_unit", "El valor i la unitat de càrrega van junts.")
    if dose.load_value is not None and dose.load_value < 0:
        _add(errors, f"{path}.load_value", "La càrrega no pot ser negativa.")
    if dose.load_unit and dose.load_unit not in PhysicalExercisePrescription.LoadUnit.values:
        _add(errors, f"{path}.load_unit", "La unitat de càrrega no és vàlida.")
    if dose.intensity_metric not in PhysicalExercisePrescription.IntensityMetric.values:
        _add(errors, f"{path}.intensity_metric", "La mètrica d'intensitat no és vàlida.")
    if dose.intensity_metric == PhysicalExercisePrescription.IntensityMetric.NONE:
        if dose.intensity_value is not None:
            _add(errors, f"{path}.intensity_value", "Cal seleccionar una mètrica d'intensitat.")
    elif dose.intensity_value is not None and dose.intensity_value < 0:
        _add(errors, f"{path}.intensity_value", "La intensitat no pot ser negativa.")
    elif dose.intensity_metric in {
        PhysicalExercisePrescription.IntensityMetric.RPE,
        PhysicalExercisePrescription.IntensityMetric.RIR,
    } and dose.intensity_value > 10:
        _add(errors, f"{path}.intensity_value", "RPE i RIR han d'estar entre 0 i 10.")
    elif (
        dose.intensity_metric == PhysicalExercisePrescription.IntensityMetric.PERCENT_1RM
        and dose.intensity_value > 200
    ):
        _add(errors, f"{path}.intensity_value", "El percentatge d'1RM no pot superar 200.")
    if dose.concentric_intent not in PhysicalExercisePrescription.ConcentricIntent.values:
        _add(errors, f"{path}.concentric_intent", "La intenció concèntrica no és vàlida.")
    if not isinstance(dose.rest_between_sets_seconds, int) or dose.rest_between_sets_seconds < 0:
        _add(errors, f"{path}.rest_between_sets_seconds", "El descans no pot ser negatiu.")


def _validate_adjustment(errors, path, adjustment: AthleteAdjustmentProposal, participants):
    if not isinstance(adjustment, AthleteAdjustmentProposal):
        _add(errors, path, "L'ajustament no compleix el contracte AthleteAdjustmentProposal.")
        return
    if adjustment.participant_plan_id not in participants:
        _add(errors, f"{path}.participant_plan_id", "El gimnasta no participa en el bloc.")
    if not adjustment.rationale.strip():
        _add(errors, f"{path}.rationale", "L'ajustament necessita una justificació.")
    for field_name in ("sets", "repetitions", "duration_seconds"):
        value = getattr(adjustment, field_name)
        if value is not None and (not isinstance(value, int) or value < 1):
            _add(errors, f"{path}.{field_name}", "El valor ha de ser un enter positiu.")
    if (adjustment.load_value is None) != (not adjustment.load_unit):
        _add(errors, f"{path}.load_unit", "El valor i la unitat de càrrega van junts.")
    if adjustment.load_value is not None and adjustment.load_value < 0:
        _add(errors, f"{path}.load_value", "La càrrega no pot ser negativa.")
    if adjustment.load_unit and adjustment.load_unit not in PhysicalExercisePrescription.LoadUnit.values:
        _add(errors, f"{path}.load_unit", "La unitat de càrrega no és vàlida.")
    if adjustment.intensity_metric and adjustment.intensity_metric not in PhysicalExercisePrescription.IntensityMetric.values:
        _add(errors, f"{path}.intensity_metric", "La mètrica d'intensitat no és vàlida.")
    if adjustment.intensity_value is not None and not adjustment.intensity_metric:
        _add(errors, f"{path}.intensity_metric", "Cal indicar la mètrica d'intensitat.")
    if adjustment.intensity_value is not None and adjustment.intensity_value < 0:
        _add(errors, f"{path}.intensity_value", "La intensitat no pot ser negativa.")
    if adjustment.rest_between_sets_seconds is not None and adjustment.rest_between_sets_seconds < 0:
        _add(errors, f"{path}.rest_between_sets_seconds", "El descans no pot ser negatiu.")
    values = (
        adjustment.replacement_exercise_revision_id,
        adjustment.sets,
        adjustment.repetitions,
        adjustment.duration_seconds,
        adjustment.load_value,
        adjustment.intensity_value,
        adjustment.rest_between_sets_seconds,
        adjustment.adaptation_notes.strip(),
    )
    if not any(value is not None and value != "" for value in values):
        _add(errors, path, "L'ajustament no modifica cap element de la prescripció.")


def referenced_exercise_revision_ids(proposal):
    identifiers = set()
    for item in proposal.items:
        if not isinstance(item, BlockItemProposal):
            continue
        if isinstance(item.dose, ExerciseDoseProposal):
            identifiers.add(item.dose.exercise_revision_id)
        identifiers.update(
            alternative.exercise_revision_id
            for alternative in item.alternatives
            if isinstance(alternative, ExerciseAlternativeProposal)
        )
        identifiers.update(
            adjustment.replacement_exercise_revision_id
            for adjustment in item.athlete_adjustments
            if isinstance(adjustment, AthleteAdjustmentProposal)
            and adjustment.replacement_exercise_revision_id
        )
    return identifiers


def validate_block_generation_proposal(
    proposal,
    *,
    revision=None,
    exercise_owner=None,
    require_validated_exercises=False,
):
    if not isinstance(proposal, BlockGenerationProposal):
        raise ValidationError("La proposta no compleix el contracte BlockGenerationProposal.")
    validate_block_generation_request(proposal.request, revision=revision)
    errors = {}
    if proposal.contract_version != "1.0":
        _add(errors, "contract_version", "La versió del contracte no està suportada.")
    if not proposal.items:
        _add(errors, "items", "La proposta necessita almenys un ítem.")
    positions = [
        item.sequence_index
        for item in proposal.items
        if isinstance(item, BlockItemProposal)
    ]
    if any(not isinstance(position, int) or position < 1 for position in positions):
        _add(errors, "items.sequence_index", "Les posicions han de ser enters positius.")
    if len(positions) != len(set(positions)):
        _add(errors, "items.sequence_index", "No es poden repetir posicions.")
    budget_seconds = proposal.request.planned_duration_minutes * 60
    if (
        not isinstance(proposal.estimated_duration_seconds, int)
        or proposal.estimated_duration_seconds < 1
        or proposal.estimated_duration_seconds > budget_seconds
    ):
        _add(errors, "estimated_duration_seconds", "La durada estimada ha de cabre dins del bloc.")
    if not isinstance(proposal.estimated_load, BlockLoadEstimate):
        _add(errors, "estimated_load", "La càrrega no compleix el contracte BlockLoadEstimate.")
    else:
        for field_name in (
            "mechanical_impact",
            "neuromuscular",
            "metabolic",
            "coordinative",
        ):
            value = getattr(proposal.estimated_load, field_name)
            if not isinstance(value, Decimal) or not (Decimal("0") <= value <= Decimal("5")):
                _add(
                    errors,
                    f"estimated_load.{field_name}",
                    "La dimensió de càrrega ha de ser un decimal entre 0 i 5.",
                )
    if not isinstance(proposal.coverage, BlockCoverage):
        _add(errors, "coverage", "La cobertura no compleix el contracte BlockCoverage.")
    elif proposal.request.objective.primary_quality not in proposal.coverage.physical_qualities:
        _add(errors, "coverage.physical_qualities", "La proposta no cobreix la qualitat principal.")
    if proposal.unmet_constraints:
        _add(errors, "unmet_constraints", "No es pot persistir una proposta amb restriccions incomplertes.")
    hard = _normalized(proposal.request.hard_constraints)
    satisfied = _normalized(proposal.satisfied_constraints)
    if not hard.issubset(satisfied):
        _add(errors, "satisfied_constraints", "No s'han satisfet totes les restriccions obligatòries.")
    if proposal.confidence is not None:
        if not isinstance(proposal.confidence, Decimal):
            _add(errors, "confidence", "La confiança ha de ser un decimal.")
        elif not (Decimal("0") <= proposal.confidence <= Decimal("1")):
            _add(errors, "confidence", "La confiança ha d'estar entre 0 i 1.")

    participants = set(proposal.request.participant_plan_ids)
    for item_index, item in enumerate(proposal.items):
        path = f"items[{item_index}]"
        if not isinstance(item, BlockItemProposal):
            _add(errors, path, "L'ítem no compleix el contracte BlockItemProposal.")
            continue
        if item.item_type not in TrainingSessionItem.ItemType.values:
            _add(errors, f"{path}.item_type", "El tipus d'ítem no és vàlid.")
        if not isinstance(item.title, str) or not item.title.strip():
            _add(errors, f"{path}.title", "L'ítem necessita un nom.")
        elif len(item.title) > 180:
            _add(errors, f"{path}.title", "El nom de l'ítem no pot superar 180 caràcters.")
        if item.planned_duration_seconds is not None and item.planned_duration_seconds < 1:
            _add(errors, f"{path}.planned_duration_seconds", "La durada ha de ser positiva.")
        if not isinstance(item.rest_after_seconds, int) or item.rest_after_seconds < 0:
            _add(errors, f"{path}.rest_after_seconds", "El descans no pot ser negatiu.")
        is_physical = item.item_type == TrainingSessionItem.ItemType.PHYSICAL_EXERCISE
        if is_physical:
            if item.dose is None:
                _add(errors, f"{path}.dose", "L'exercici físic necessita una prescripció.")
            else:
                _validate_dose(errors, f"{path}.dose", item.dose)
            if not isinstance(item.selection_rationale, str) or not item.selection_rationale.strip():
                _add(errors, f"{path}.selection_rationale", "Cal justificar la selecció de l'exercici.")
        elif item.dose or item.alternatives or item.athlete_adjustments:
            _add(errors, path, "Només un exercici físic pot tenir dosi, alternatives o ajustaments.")

        alternative_ids = []
        for alternative_index, alternative in enumerate(item.alternatives):
            alternative_path = f"{path}.alternatives[{alternative_index}]"
            if not isinstance(alternative, ExerciseAlternativeProposal):
                _add(
                    errors,
                    alternative_path,
                    "L'alternativa no compleix el contracte ExerciseAlternativeProposal.",
                )
                continue
            alternative_ids.append(alternative.exercise_revision_id)
            if alternative.trigger not in SessionItemAlternative.Trigger.values:
                _add(errors, f"{alternative_path}.trigger", "El desencadenant no és vàlid.")
            if not isinstance(alternative.priority, int) or alternative.priority < 1:
                _add(errors, f"{alternative_path}.priority", "La prioritat ha de ser positiva.")
            if not alternative.rationale.strip():
                _add(errors, f"{alternative_path}.rationale", "L'alternativa necessita una justificació.")
        if len(alternative_ids) != len(set(alternative_ids)):
            _add(errors, f"{path}.alternatives", "No es pot repetir un exercici alternatiu.")
        if item.dose and item.dose.exercise_revision_id in alternative_ids:
            _add(errors, f"{path}.alternatives", "L'exercici principal no pot ser també una alternativa.")

        adjustment_participants = []
        for adjustment_index, adjustment in enumerate(item.athlete_adjustments):
            adjustment_path = f"{path}.athlete_adjustments[{adjustment_index}]"
            if isinstance(adjustment, AthleteAdjustmentProposal):
                adjustment_participants.append(adjustment.participant_plan_id)
            _validate_adjustment(errors, adjustment_path, adjustment, participants)
        if len(adjustment_participants) != len(set(adjustment_participants)):
            _add(errors, f"{path}.athlete_adjustments", "Només hi pot haver un ajustament per gimnasta.")

    exercise_ids = referenced_exercise_revision_ids(proposal)
    if exercise_ids:
        revisions = ExerciseRevision.objects.filter(pk__in=exercise_ids).select_related(
            "exercise__catalog"
        )
        found = {exercise.pk: exercise for exercise in revisions}
        missing = exercise_ids - found.keys()
        if missing:
            _add(errors, "exercise_revisions", f"No existeixen les revisions: {sorted(missing)}.")
        for exercise_revision in found.values():
            if exercise_revision.editorial_status == "retired":
                _add(errors, "exercise_revisions", f"La revisió {exercise_revision.pk} està retirada.")
            if exercise_owner is not None and exercise_revision.exercise.catalog.owner_id != exercise_owner.pk:
                _add(errors, "exercise_revisions", f"La revisió {exercise_revision.pk} no pertany al catàleg de l'entrenador.")
            if require_validated_exercises and exercise_revision.editorial_status != "validated":
                _add(errors, "exercise_revisions", f"La revisió {exercise_revision.pk} encara no està validada.")
    if errors:
        raise ValidationError(errors)
    return proposal
