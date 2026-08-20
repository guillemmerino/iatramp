from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q

from core.models import Person
from organizations.models import Organization

from .base import CleanOnSaveModel


class TrainingSession(CleanOnSaveModel):
    class Discipline(models.TextChoices):
        TRAMPOLINE = "trampoline", "Trampolí"
        DMT = "dmt", "Doble minitrampolí"
        TUMBLING = "tumbling", "Tumbling"
        GENERAL = "general", "General"

    class Scope(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        GROUP = "group", "Grup"

    class LifecycleStatus(models.TextChoices):
        SCHEDULED = "scheduled", "Programada"
        IN_PROGRESS = "in_progress", "En curs"
        COMPLETED = "completed", "Completada"
        CANCELLED = "cancelled", "Cancel·lada"

    class CreationOrigin(models.TextChoices):
        MANUAL = "manual", "Manual"
        GENERATED = "generated", "Generada"
        IMPORTED = "imported", "Importada"

    organization = models.ForeignKey(
        Organization, on_delete=models.PROTECT, related_name="training_sessions"
    )
    gym = models.ForeignKey(
        "iatrain.Gym",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="training_sessions",
    )
    training_group = models.ForeignKey(
        "iatrain.TrainingGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="training_sessions",
    )
    scheduled_start = models.DateTimeField()
    expected_duration_minutes = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(1),)
    )
    discipline = models.CharField(max_length=20, choices=Discipline.choices)
    session_scope = models.CharField(max_length=20, choices=Scope.choices)
    responsible_coach = models.ForeignKey(
        "iatrain.CoachProfile",
        on_delete=models.PROTECT,
        related_name="responsible_training_sessions",
    )
    lifecycle_status = models.CharField(
        max_length=20,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.SCHEDULED,
    )
    creation_origin = models.CharField(
        max_length=20,
        choices=CreationOrigin.choices,
        default=CreationOrigin.MANUAL,
    )
    created_by = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="created_training_sessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-scheduled_start", "-id")
        indexes = [
            models.Index(
                fields=("organization", "scheduled_start"),
                name="iatrain_session_org_start_idx",
            ),
            models.Index(
                fields=("responsible_coach", "scheduled_start"),
                name="iatrain_session_coach_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.responsible_coach_id and not self.responsible_coach.is_active:
            errors["responsible_coach"] = "L'entrenador responsable ha d'estar actiu."
        if self.training_group_id and self.organization_id:
            if self.training_group.organization_id != self.organization_id:
                errors["training_group"] = "El grup ha de pertànyer a l'organització de la sessió."
        if self.session_scope == self.Scope.GROUP and not self.training_group_id:
            errors["training_group"] = "Una sessió de grup necessita un grup d'entrenament."
        if self.session_scope == self.Scope.INDIVIDUAL and self.training_group_id:
            errors["training_group"] = "Una sessió individual no pot quedar vinculada a un grup."
        if self.gym_id and self.organization_id:
            if not self.gym.organization_links.filter(
                organization_id=self.organization_id, is_active=True
            ).exists():
                errors["gym"] = "El gimnàs no està vinculat activament a l'organització."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.organization} · {self.scheduled_start:%Y-%m-%d %H:%M}"


class TrainingSessionRevision(CleanOnSaveModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Esborrany"
        PROPOSED = "proposed", "Proposada"
        APPROVED = "approved", "Aprovada"
        SUPERSEDED = "superseded", "Substituïda"
        REJECTED = "rejected", "Rebutjada"

    session = models.ForeignKey(
        TrainingSession, on_delete=models.PROTECT, related_name="revisions"
    )
    revision_number = models.PositiveSmallIntegerField(validators=(MinValueValidator(1),))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="superseded_by",
    )
    title = models.CharField(max_length=200)
    general_objective = models.TextField(blank=True, default="")
    planned_duration_minutes = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(1),)
    )
    creation_origin = models.CharField(
        max_length=20,
        choices=TrainingSession.CreationOrigin.choices,
        default=TrainingSession.CreationOrigin.MANUAL,
    )
    change_reason = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="created_training_session_revisions"
    )
    approved_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_training_session_revisions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("session_id", "-revision_number", "-id")
        constraints = [
            models.UniqueConstraint(
                fields=("session", "revision_number"), name="iatrain_session_rev_uniq_number"
            ),
            models.UniqueConstraint(
                fields=("session",),
                condition=Q(status="approved"),
                name="iatrain_session_one_approved_rev",
            ),
            models.CheckConstraint(
                check=~Q(supersedes=F("id")), name="iatrain_session_rev_no_self_sup"
            ),
        ]
        indexes = [
            models.Index(
                fields=("session", "status"), name="iatrain_session_rev_status_idx"
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        previous = None
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
        if self._state.adding and self.status != self.Status.DRAFT:
            errors["status"] = "Una versió nova sempre entra com a esborrany."
        if previous and previous.status != self.status:
            allowed_transitions = {
                self.Status.DRAFT: {self.Status.PROPOSED},
                self.Status.PROPOSED: {
                    self.Status.DRAFT,
                    self.Status.APPROVED,
                    self.Status.REJECTED,
                },
                self.Status.APPROVED: {self.Status.SUPERSEDED},
                self.Status.REJECTED: {self.Status.DRAFT},
                self.Status.SUPERSEDED: set(),
            }
            if self.status not in allowed_transitions.get(previous.status, set()):
                errors["status"] = "Aquesta transició d'estat de la versió no és vàlida."
        if previous and previous.status != self.Status.DRAFT:
            immutable_fields = (
                "session_id",
                "revision_number",
                "supersedes_id",
                "title",
                "general_objective",
                "planned_duration_minutes",
                "creation_origin",
                "change_reason",
                "created_by_id",
            )
            if any(getattr(previous, field) != getattr(self, field) for field in immutable_fields):
                errors["status"] = "Una versió que ja no és esborrany no es pot editar."
        if self.supersedes_id:
            if self.pk and self.supersedes_id == self.pk:
                errors["supersedes"] = "Una versió no es pot substituir a si mateixa."
            elif self.supersedes.session_id != self.session_id:
                errors["supersedes"] = "Només es pot substituir una versió de la mateixa sessió."
            elif self.supersedes.revision_number >= self.revision_number:
                errors["revision_number"] = "La nova versió ha de tenir un número superior."
        approval_complete = bool(self.approved_by_id and self.approved_at)
        if self.status == self.Status.APPROVED and not approval_complete:
            errors["approved_by"] = "Una versió aprovada necessita autoria i data d'aprovació."
        if self.status not in {self.Status.APPROVED, self.Status.SUPERSEDED} and (
            self.approved_by_id or self.approved_at
        ):
            errors["approved_by"] = "Només una versió aprovada pot conservar dades d'aprovació."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        if self.status != self.Status.DRAFT:
            raise ValidationError("Només es pot eliminar una versió en esborrany.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.title} · v{self.revision_number}"
