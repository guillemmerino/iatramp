from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import Person

from .base import CleanOnSaveModel
from .planning import PhysicalExercisePrescription


class TrainingSessionExecution(CleanOnSaveModel):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "No iniciada"
        IN_PROGRESS = "in_progress", "En curs"
        COMPLETED = "completed", "Completada"
        ABORTED = "aborted", "Interrompuda"

    session = models.OneToOneField(
        "iatrain.TrainingSession",
        on_delete=models.PROTECT,
        related_name="execution",
    )
    approved_revision = models.ForeignKey(
        "iatrain.TrainingSessionRevision",
        on_delete=models.PROTECT,
        related_name="executions",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_STARTED
    )
    supervised_by = models.ForeignKey(
        "iatrain.CoachProfile",
        on_delete=models.PROTECT,
        related_name="supervised_training_executions",
    )
    general_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("status", "started_at"), name="iatrain_exec_status_idx")
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.approved_revision_id and self.session_id:
            if self.approved_revision.session_id != self.session_id:
                errors["approved_revision"] = "La versió aprovada no pertany a aquesta sessió."
            elif self.approved_revision.status != "approved":
                errors["approved_revision"] = "Només es pot executar una versió aprovada."
        if self.supervised_by_id and not self.supervised_by.is_active:
            errors["supervised_by"] = "L'entrenador supervisor ha d'estar actiu."
        if self.status == self.Status.NOT_STARTED and (self.started_at or self.finished_at):
            errors["started_at"] = "Una execució no iniciada no pot tenir dates d'execució."
        if self.status in {self.Status.IN_PROGRESS, self.Status.COMPLETED, self.Status.ABORTED}:
            if not self.started_at:
                errors["started_at"] = "Una execució iniciada necessita data d'inici."
        if self.status == self.Status.IN_PROGRESS and self.finished_at:
            errors["finished_at"] = "Una execució en curs encara no pot tenir data final."
        if self.status in {self.Status.COMPLETED, self.Status.ABORTED} and not self.finished_at:
            errors["finished_at"] = "Una execució finalitzada necessita data final."
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            errors["finished_at"] = "La data final no pot ser anterior a l'inici."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Execució · {self.session}"


class SessionAttendance(CleanOnSaveModel):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        ABSENT = "absent", "Absent"
        PARTIAL = "partial", "Parcial"
        EXCUSED = "excused", "Justificada"

    execution = models.ForeignKey(
        TrainingSessionExecution, on_delete=models.PROTECT, related_name="attendance"
    )
    athlete_profile = models.ForeignKey(
        "iatrain.AthleteProfile",
        on_delete=models.PROTECT,
        related_name="training_attendance",
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    joined_at = models.DateTimeField(null=True, blank=True)
    left_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("execution_id", "athlete_profile_id")
        constraints = [
            models.UniqueConstraint(
                fields=("execution", "athlete_profile"),
                name="iatrain_execution_attendance_uniq",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.execution_id and self.athlete_profile_id:
            if not self.execution.approved_revision.participant_plans.filter(
                athlete_profile_id=self.athlete_profile_id
            ).exists():
                errors["athlete_profile"] = "El gimnasta no forma part de la planificació aprovada."
        if self.joined_at and self.left_at and self.left_at < self.joined_at:
            errors["left_at"] = "L'hora de sortida no pot ser anterior a l'entrada."
        if self.status in {self.Status.ABSENT, self.Status.EXCUSED} and (
            self.joined_at or self.left_at
        ):
            errors["joined_at"] = "Una absència no pot contenir hores de participació."
        if errors:
            raise ValidationError(errors)


class TrainingItemResult(CleanOnSaveModel):
    class CompletionStatus(models.TextChoices):
        COMPLETED = "completed", "Completat"
        PARTIAL = "partial", "Parcial"
        SKIPPED = "skipped", "Omes"
        SUBSTITUTED = "substituted", "Substituït"
        STOPPED = "stopped", "Aturat"

    class PainResponse(models.TextChoices):
        NONE = "none", "Sense dolor"
        REPORTED = "reported", "Dolor comunicat"
        STOPPED = "stopped", "Aturat per dolor"

    execution = models.ForeignKey(
        TrainingSessionExecution, on_delete=models.PROTECT, related_name="item_results"
    )
    session_item = models.ForeignKey(
        "iatrain.TrainingSessionItem",
        on_delete=models.PROTECT,
        related_name="execution_results",
    )
    athlete_profile = models.ForeignKey(
        "iatrain.AthleteProfile",
        on_delete=models.PROTECT,
        related_name="training_item_results",
    )
    completion_status = models.CharField(max_length=20, choices=CompletionStatus.choices)
    exercise_revision_performed = models.ForeignKey(
        "iatrain_exercises.ExerciseRevision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="performed_training_results",
    )
    actual_sets = models.PositiveSmallIntegerField(null=True, blank=True)
    actual_repetitions = models.PositiveSmallIntegerField(null=True, blank=True)
    actual_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    actual_load_value = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=(MinValueValidator(0),),
    )
    actual_load_unit = models.CharField(
        max_length=30,
        choices=PhysicalExercisePrescription.LoadUnit.choices,
        blank=True,
        default="",
    )
    perceived_exertion = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(10)),
    )
    execution_quality = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=(MinValueValidator(1), MaxValueValidator(5))
    )
    pain_response = models.CharField(
        max_length=20, choices=PainResponse.choices, default=PainResponse.NONE
    )
    athlete_feedback = models.TextField(blank=True, default="")
    coach_feedback = models.TextField(blank=True, default="")
    recorded_by = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="recorded_training_item_results"
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("execution_id", "session_item_id", "athlete_profile_id")
        constraints = [
            models.UniqueConstraint(
                fields=("execution", "session_item", "athlete_profile"),
                name="iatrain_item_result_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("athlete_profile", "recorded_at"),
                name="iatrain_result_athlete_idx",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.execution_id and self.session_item_id:
            if self.session_item.block.session_revision_id != self.execution.approved_revision_id:
                errors["session_item"] = "L'ítem no pertany a la versió que s'està executant."
        if self.execution_id and self.athlete_profile_id:
            if not self.execution.approved_revision.participant_plans.filter(
                athlete_profile_id=self.athlete_profile_id
            ).exists():
                errors["athlete_profile"] = "El gimnasta no forma part de la planificació aprovada."
        if bool(self.actual_load_value is not None) != bool(self.actual_load_unit):
            errors["actual_load_unit"] = "El valor i la unitat de càrrega s'han d'indicar conjuntament."
        if self.session_item_id and self.session_item.item_type == "physical_exercise":
            if self.completion_status not in {self.CompletionStatus.SKIPPED, self.CompletionStatus.STOPPED}:
                if not self.exercise_revision_performed_id:
                    errors["exercise_revision_performed"] = (
                        "Cal indicar quin exercici físic s'ha executat."
                    )
        elif self.exercise_revision_performed_id:
            errors["exercise_revision_performed"] = (
                "Un ítem no físic no pot registrar un exercici físic executat."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.athlete_profile} · {self.session_item} · {self.get_completion_status_display()}"
