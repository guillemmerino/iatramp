from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .base import RevisionOwnedModel


class SessionParticipantPlan(RevisionOwnedModel):
    class Participation(models.TextChoices):
        FULL = "full", "Completa"
        PARTIAL = "partial", "Parcial"
        OPTIONAL = "optional", "Opcional"

    session_revision = models.ForeignKey(
        "iatrain.TrainingSessionRevision",
        on_delete=models.PROTECT,
        related_name="participant_plans",
    )
    athlete_profile = models.ForeignKey(
        "iatrain.AthleteProfile",
        on_delete=models.PROTECT,
        related_name="planned_training_sessions",
    )
    expected_participation = models.CharField(
        max_length=20, choices=Participation.choices, default=Participation.FULL
    )
    individual_objective = models.TextField(blank=True, default="")
    planning_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("session_revision_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("session_revision", "athlete_profile"),
                name="iatrain_plan_participant_uniq",
            )
        ]

    def owning_revision(self):
        return self.session_revision if self.session_revision_id else None

    def clean(self):
        super().clean()
        if self.athlete_profile_id and not self.athlete_profile.is_active:
            raise ValidationError({"athlete_profile": "El perfil del gimnasta ha d'estar actiu."})

    def __str__(self):
        return f"{self.athlete_profile} · {self.session_revision}"


class SessionGoal(RevisionOwnedModel):
    class Domain(models.TextChoices):
        PHYSICAL = "physical", "Físic"
        TECHNICAL = "technical", "Tècnic"
        RECOVERY = "recovery", "Recuperació"
        ASSESSMENT = "assessment", "Avaluació"
        GENERAL = "general", "General"

    class Priority(models.TextChoices):
        PRIMARY = "primary", "Principal"
        SECONDARY = "secondary", "Secundari"
        OPTIONAL = "optional", "Opcional"

    class Source(models.TextChoices):
        COACH = "coach", "Entrenador"
        PLAN = "plan", "Planificació"
        ASSESSMENT = "assessment", "Avaluació"
        SYSTEM = "system", "Sistema"

    session_revision = models.ForeignKey(
        "iatrain.TrainingSessionRevision", on_delete=models.PROTECT, related_name="goals"
    )
    domain = models.CharField(max_length=20, choices=Domain.choices)
    code = models.SlugField(max_length=80)
    description = models.TextField()
    priority = models.CharField(max_length=20, choices=Priority.choices)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.COACH)
    rationale = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("session_revision_id", "priority", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("session_revision", "domain", "code"),
                name="iatrain_session_goal_uniq",
            )
        ]

    def owning_revision(self):
        return self.session_revision if self.session_revision_id else None

    def clean(self):
        self.code = str(self.code or "").strip().lower().replace(" ", "-")
        super().clean()
        if not self.description.strip():
            raise ValidationError({"description": "L'objectiu necessita una descripció."})

    def __str__(self):
        return f"{self.get_domain_display()} · {self.description[:60]}"


class TrainingBlock(RevisionOwnedModel):
    class Role(models.TextChoices):
        PREPARATION = "preparation", "Preparació"
        MAIN = "main", "Principal"
        COMPLEMENTARY = "complementary", "Complementari"
        RECOVERY = "recovery", "Recuperació"
        ASSESSMENT = "assessment", "Avaluació"

    class Domain(models.TextChoices):
        PHYSICAL = "physical", "Físic"
        TECHNICAL = "technical", "Tècnic"
        MIXED = "mixed", "Mixt"
        GENERAL = "general", "General"

    class ExecutionMode(models.TextChoices):
        SEQUENTIAL = "sequential", "Seqüencial"
        CIRCUIT = "circuit", "Circuit"
        STATIONS = "stations", "Estacions"
        SUPERSET = "superset", "Supersèrie"
        PARALLEL = "parallel", "Paral·lel"

    session_revision = models.ForeignKey(
        "iatrain.TrainingSessionRevision", on_delete=models.PROTECT, related_name="blocks"
    )
    sequence_index = models.PositiveSmallIntegerField(validators=(MinValueValidator(1),))
    name = models.CharField(max_length=160)
    block_role = models.CharField(max_length=20, choices=Role.choices)
    domain = models.CharField(max_length=20, choices=Domain.choices)
    execution_mode = models.CharField(
        max_length=20, choices=ExecutionMode.choices, default=ExecutionMode.SEQUENTIAL
    )
    planned_duration_minutes = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(1),)
    )
    transition_duration_seconds = models.PositiveSmallIntegerField(default=0)
    objective = models.TextField(blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    is_optional = models.BooleanField(default=False)
    rounds = models.PositiveSmallIntegerField(default=1, validators=(MinValueValidator(1),))
    rest_between_rounds_seconds = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("session_revision_id", "sequence_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("session_revision", "sequence_index"),
                name="iatrain_session_block_order_uniq",
            )
        ]

    def owning_revision(self):
        return self.session_revision if self.session_revision_id else None

    def __str__(self):
        return f"{self.sequence_index}. {self.name}"


class BlockParticipantAssignment(RevisionOwnedModel):
    """Participation decision for one gymnast within one training block."""

    class Mode(models.TextChoices):
        SHARED = "shared", "Prescripció compartida"
        PERSONALIZED = "personalized", "Prescripció personalitzada"
        EXCLUDED = "excluded", "Exclosa del bloc"

    block = models.ForeignKey(
        TrainingBlock, on_delete=models.CASCADE, related_name="participant_assignments"
    )
    participant_plan = models.ForeignKey(
        SessionParticipantPlan,
        on_delete=models.PROTECT,
        related_name="block_assignments",
    )
    mode = models.CharField(max_length=20, choices=Mode.choices)
    rationale = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("block_id", "participant_plan_id")
        constraints = [
            models.UniqueConstraint(
                fields=("block", "participant_plan"),
                name="iatrain_block_participant_uniq",
            )
        ]

    def owning_revision(self):
        return self.block.session_revision if self.block_id else None

    def clean(self):
        super().clean()
        if self.block_id and self.participant_plan_id:
            if self.block.session_revision_id != self.participant_plan.session_revision_id:
                raise ValidationError(
                    {"participant_plan": "El bloc i el participant han de ser de la mateixa versió."}
                )


class TrainingSessionItem(RevisionOwnedModel):
    class ItemType(models.TextChoices):
        PHYSICAL_EXERCISE = "physical_exercise", "Exercici físic"
        INSTRUCTION = "instruction", "Instrucció"
        RECOVERY = "recovery", "Recuperació"
        BREAK = "break", "Pausa"
        TECHNICAL_TASK = "technical_task", "Tasca tècnica"
        TECHNICAL_ELEMENT = "technical_element", "Element tècnic"
        SEQUENCE = "sequence", "Seqüència"
        ASSESSMENT = "assessment", "Avaluació"

    block = models.ForeignKey(
        TrainingBlock, on_delete=models.PROTECT, related_name="items"
    )
    sequence_index = models.PositiveSmallIntegerField(validators=(MinValueValidator(1),))
    item_type = models.CharField(max_length=30, choices=ItemType.choices)
    title = models.CharField(max_length=180)
    instructions = models.TextField(blank=True, default="")
    coaching_cues = models.TextField(blank=True, default="")
    planned_duration_seconds = models.PositiveIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1),)
    )
    rest_after_seconds = models.PositiveSmallIntegerField(default=0)
    selection_rationale = models.TextField(blank=True, default="")
    is_optional = models.BooleanField(default=False)

    class Meta:
        ordering = ("block_id", "sequence_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("block", "sequence_index"), name="iatrain_session_item_order_uniq"
            )
        ]

    def owning_revision(self):
        return self.block.session_revision if self.block_id else None

    def __str__(self):
        return f"{self.block} · {self.sequence_index}. {self.title}"


class PhysicalExercisePrescription(RevisionOwnedModel):
    class DoseMode(models.TextChoices):
        REPETITIONS = "repetitions", "Repeticions"
        DURATION = "duration", "Durada"
        DISTANCE = "distance", "Distància"
        HOLD = "hold", "Manteniment"
        ASSISTED = "assisted", "Assistida"

    class DistanceUnit(models.TextChoices):
        METRE = "m", "Metres"
        KILOMETRE = "km", "Quilòmetres"

    class LoadUnit(models.TextChoices):
        KILOGRAM = "kg", "Quilograms"
        PERCENT_BODYWEIGHT = "percent_bodyweight", "% del pes corporal"
        OTHER = "other", "Altres"

    class IntensityMetric(models.TextChoices):
        NONE = "none", "Sense mètrica"
        RPE = "rpe", "RPE"
        RIR = "rir", "RIR"
        PERCENT_1RM = "percent_1rm", "% 1RM"
        TECHNICAL_QUALITY = "technical_quality", "Qualitat tècnica"
        BODYWEIGHT = "bodyweight", "Pes corporal"
        ASSISTED = "assisted", "Assistida"

    class ConcentricIntent(models.TextChoices):
        CONTROLLED = "controlled", "Controlada"
        FAST = "fast", "Ràpida"
        EXPLOSIVE = "explosive", "Explosiva"

    session_item = models.OneToOneField(
        TrainingSessionItem,
        on_delete=models.CASCADE,
        related_name="physical_prescription",
    )
    exercise_revision = models.ForeignKey(
        "iatrain_exercises.ExerciseRevision",
        on_delete=models.PROTECT,
        related_name="training_prescriptions",
    )
    dose_mode = models.CharField(max_length=20, choices=DoseMode.choices)
    sets = models.PositiveSmallIntegerField(default=1, validators=(MinValueValidator(1),))
    repetitions = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1),)
    )
    duration_seconds = models.PositiveIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1),)
    )
    distance = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=(MinValueValidator(0.01),),
    )
    distance_unit = models.CharField(
        max_length=10, choices=DistanceUnit.choices, blank=True, default=""
    )
    load_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=(MinValueValidator(0),),
    )
    load_unit = models.CharField(
        max_length=30, choices=LoadUnit.choices, blank=True, default=""
    )
    intensity_metric = models.CharField(
        max_length=30, choices=IntensityMetric.choices, default=IntensityMetric.NONE
    )
    intensity_value = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=(MinValueValidator(0),),
    )
    tempo_eccentric_seconds = models.PositiveSmallIntegerField(null=True, blank=True)
    tempo_pause_seconds = models.PositiveSmallIntegerField(null=True, blank=True)
    tempo_concentric_seconds = models.PositiveSmallIntegerField(null=True, blank=True)
    concentric_intent = models.CharField(
        max_length=20,
        choices=ConcentricIntent.choices,
        default=ConcentricIntent.CONTROLLED,
    )
    rest_between_sets_seconds = models.PositiveSmallIntegerField(default=0)
    execution_notes = models.TextField(blank=True, default="")

    def owning_revision(self):
        return self.session_item.block.session_revision if self.session_item_id else None

    def clean(self):
        super().clean()
        errors = {}
        if self.session_item_id and self.session_item.item_type != TrainingSessionItem.ItemType.PHYSICAL_EXERCISE:
            errors["session_item"] = "La prescripció física necessita un ítem d'exercici físic."
        required_field = {
            self.DoseMode.REPETITIONS: "repetitions",
            self.DoseMode.DURATION: "duration_seconds",
            self.DoseMode.HOLD: "duration_seconds",
            self.DoseMode.DISTANCE: "distance",
        }.get(self.dose_mode)
        if required_field and getattr(self, required_field) is None:
            errors[required_field] = "Aquesta dosi necessita un valor."
        if self.dose_mode == self.DoseMode.DISTANCE and not self.distance_unit:
            errors["distance_unit"] = "La distància necessita una unitat."
        if bool(self.load_value is not None) != bool(self.load_unit):
            errors["load_unit"] = "El valor i la unitat de càrrega s'han d'indicar conjuntament."
        if self.intensity_metric == self.IntensityMetric.NONE and self.intensity_value is not None:
            errors["intensity_value"] = "Cal seleccionar una mètrica d'intensitat."
        if self.intensity_metric == self.IntensityMetric.RPE and self.intensity_value is not None:
            if self.intensity_value > 10:
                errors["intensity_value"] = "L'RPE ha d'estar entre 0 i 10."
        if self.intensity_metric == self.IntensityMetric.RIR and self.intensity_value is not None:
            if self.intensity_value > 10:
                errors["intensity_value"] = "El RIR ha d'estar entre 0 i 10."
        if self.intensity_metric == self.IntensityMetric.PERCENT_1RM and self.intensity_value is not None:
            if self.intensity_value > 200:
                errors["intensity_value"] = "El percentatge d'1RM ha d'estar entre 0 i 200."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.session_item} · {self.exercise_revision}"


class SessionItemAlternative(RevisionOwnedModel):
    class Trigger(models.TextChoices):
        EQUIPMENT = "equipment_unavailable", "Material no disponible"
        DIFFICULTY = "difficulty_too_high", "Dificultat excessiva"
        PAIN = "pain_or_restriction", "Dolor o restricció"
        LOGISTICS = "group_logistics", "Logística de grup"
        COACH = "coach_decision", "Decisió de l'entrenador"

    session_item = models.ForeignKey(
        TrainingSessionItem, on_delete=models.CASCADE, related_name="alternatives"
    )
    exercise_revision = models.ForeignKey(
        "iatrain_exercises.ExerciseRevision",
        on_delete=models.PROTECT,
        related_name="training_alternatives",
    )
    priority = models.PositiveSmallIntegerField(default=1, validators=(MinValueValidator(1),))
    trigger = models.CharField(max_length=30, choices=Trigger.choices)
    rationale = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("session_item_id", "priority", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("session_item", "exercise_revision"),
                name="iatrain_item_alternative_uniq",
            )
        ]

    def owning_revision(self):
        return self.session_item.block.session_revision if self.session_item_id else None

    def clean(self):
        super().clean()
        if self.session_item_id and self.session_item.item_type != TrainingSessionItem.ItemType.PHYSICAL_EXERCISE:
            raise ValidationError({"session_item": "Només un exercici físic pot tenir alternatives físiques."})


class SessionItemAthleteAdjustment(RevisionOwnedModel):
    class Action(models.TextChoices):
        MODIFY = "modify", "Modificar dosi"
        REPLACE = "replace", "Substituir exercici"
        SKIP = "skip", "No participa en l'ítem"

    session_item = models.ForeignKey(
        TrainingSessionItem, on_delete=models.CASCADE, related_name="athlete_adjustments"
    )
    participant_plan = models.ForeignKey(
        SessionParticipantPlan, on_delete=models.PROTECT, related_name="item_adjustments"
    )
    replacement_exercise_revision = models.ForeignKey(
        "iatrain_exercises.ExerciseRevision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="training_adjustments",
    )
    action = models.CharField(
        max_length=20, choices=Action.choices, default=Action.MODIFY
    )
    sets = models.PositiveSmallIntegerField(null=True, blank=True, validators=(MinValueValidator(1),))
    repetitions = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1),)
    )
    duration_seconds = models.PositiveIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1),)
    )
    load_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=(MinValueValidator(0),),
    )
    load_unit = models.CharField(
        max_length=30, choices=PhysicalExercisePrescription.LoadUnit.choices, blank=True, default=""
    )
    intensity_metric = models.CharField(
        max_length=30,
        choices=PhysicalExercisePrescription.IntensityMetric.choices,
        blank=True,
        default="",
    )
    intensity_value = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=(MinValueValidator(0),),
    )
    rest_between_sets_seconds = models.PositiveSmallIntegerField(null=True, blank=True)
    adaptation_notes = models.TextField(blank=True, default="")
    rationale = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("session_item_id", "participant_plan_id")
        constraints = [
            models.UniqueConstraint(
                fields=("session_item", "participant_plan"),
                name="iatrain_item_athlete_adjust_uniq",
            )
        ]

    def owning_revision(self):
        return self.session_item.block.session_revision if self.session_item_id else None

    def clean(self):
        super().clean()
        errors = {}
        if self.session_item_id and self.session_item.item_type != TrainingSessionItem.ItemType.PHYSICAL_EXERCISE:
            errors["session_item"] = "Només es pot adaptar un ítem d'exercici físic."
        if self.session_item_id and self.participant_plan_id:
            if self.session_item.block.session_revision_id != self.participant_plan.session_revision_id:
                errors["participant_plan"] = "L'adaptació i el participant han de ser de la mateixa versió."
        if bool(self.load_value is not None) != bool(self.load_unit):
            errors["load_unit"] = "El valor i la unitat de càrrega s'han d'indicar conjuntament."
        if self.intensity_value is not None and not self.intensity_metric:
            errors["intensity_metric"] = "Cal indicar la mètrica d'intensitat."
        if self.action == self.Action.REPLACE and not self.replacement_exercise_revision_id:
            errors["replacement_exercise_revision"] = "La substitució necessita un exercici."
        if self.action == self.Action.SKIP:
            has_prescription = any(
                value is not None and value != ""
                for value in (
                    self.replacement_exercise_revision_id,
                    self.sets,
                    self.repetitions,
                    self.duration_seconds,
                    self.load_value,
                    self.load_unit,
                    self.intensity_metric,
                    self.intensity_value,
                    self.rest_between_sets_seconds,
                )
            )
            if has_prescription:
                errors["action"] = "Un ítem omès no pot contenir una prescripció alternativa."
        if errors:
            raise ValidationError(errors)
