from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import Organization, Person


class TrainingContext(models.Model):
    """A bounded training workspace owned by a coach and shared by its athletes."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Esborrany"
        ACTIVE = "active", "Actiu"
        CLOSED = "closed", "Tancat"
        ARCHIVED = "archived", "Arxivat"

    name = models.CharField(max_length=180)
    purpose = models.TextField(blank=True, default="")
    discipline = models.CharField(
        max_length=80,
        default="trampoline",
        help_text="Vocabulari curt i estable, per exemple: trampoline, dmt, tumbling o general.",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="training_contexts",
    )
    responsible_coach = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="owned_training_contexts",
    )
    athletes = models.ManyToManyField(
        Person,
        blank=True,
        related_name="training_contexts",
        help_text="Un sol gimnasta per a context individual; diversos per a un context compartit.",
    )
    valid_from = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    metadata = models.JSONField(
        blank=True,
        default=dict,
        help_text="Extensions petites i no crítiques; no substitueix camps de domini nous.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-valid_from", "name", "id")
        constraints = [
            models.CheckConstraint(
                check=Q(valid_until__isnull=True) | Q(valid_until__gte=F("valid_from")),
                name="iatrain_context_dates_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("responsible_coach", "status", "valid_from"),
                name="iatrain_ctx_coach_idx",
            ),
            models.Index(
                fields=("organization", "status"),
                name="iatrain_ctx_org_idx",
            ),
            models.Index(fields=("discipline", "status"), name="iatrain_ctx_scope_idx"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not self.name.strip():
            errors["name"] = "El context ha de tenir un nom."
        if not self.discipline.strip():
            errors["discipline"] = "La disciplina no pot quedar buida."
        if self.valid_until and self.valid_until < self.valid_from:
            errors["valid_until"] = "La data de fi no pot ser anterior a la d'inici."
        if not isinstance(self.metadata, dict):
            errors["metadata"] = "Les metadades han de ser un objecte JSON."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class KnowledgeConcept(models.Model):
    """A professional knowledge node; ``kind`` intentionally remains extensible."""

    class Kind:
        SKILL = "skill"
        TECHNICAL_COMPONENT = "technical_component"
        ERROR = "error"
        EXERCISE = "exercise"
        QUALITY = "quality"
        RISK = "risk"
        GOAL = "goal"

    class EditorialStatus(models.TextChoices):
        DRAFT = "draft", "Esborrany"
        VALIDATED = "validated", "Validat"
        RETIRED = "retired", "Retirat"

    name = models.CharField(max_length=220)
    description = models.TextField(blank=True, default="")
    kind = models.CharField(
        max_length=60,
        help_text="Tipus extensible: skill, technical_component, error, exercise, quality, risk, goal…",
    )
    discipline = models.CharField(max_length=80, default="trampoline")
    editorial_status = models.CharField(
        max_length=20,
        choices=EditorialStatus.choices,
        default=EditorialStatus.DRAFT,
    )
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_knowledge_concepts",
    )
    attributes = models.JSONField(
        blank=True,
        default=dict,
        help_text="Atributs extensibles amb significat documentat; no hi desis relacions entre conceptes.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("discipline", "kind", "name", "id")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "kind",
                "discipline",
                name="iatrain_concept_uniq_name",
            ),
        ]
        indexes = [
            models.Index(
                fields=("discipline", "kind", "editorial_status"),
                name="iatrain_concept_scope_idx",
            ),
            models.Index(fields=("authored_by", "created_at"), name="iatrain_concept_author_idx"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not self.name.strip():
            errors["name"] = "El concepte ha de tenir un nom."
        if not self.kind.strip():
            errors["kind"] = "El concepte ha de tenir un tipus."
        if not self.discipline.strip():
            errors["discipline"] = "L'àmbit o disciplina no pot quedar buit."
        if not isinstance(self.attributes, dict):
            errors["attributes"] = "Els atributs han de ser un objecte JSON."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class KnowledgeRelation(models.Model):
    """A directed, editorially governed edge in the professional graph."""

    class RelationType:
        REQUIRES = "requires"
        PROGRESSES_TO = "progresses_to"
        CORRECTS = "corrects"
        CONDITIONS = "conditions"
        TRAINS = "trains"

    class EditorialStatus(models.TextChoices):
        DRAFT = "draft", "Esborrany"
        VALIDATED = "validated", "Validada"
        RETIRED = "retired", "Retirada"

    source = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.PROTECT,
        related_name="outgoing_relations",
    )
    target = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.PROTECT,
        related_name="incoming_relations",
    )
    relation_type = models.CharField(
        max_length=60,
        help_text="Tipus dirigit extensible: requires, progresses_to, corrects, conditions, trains…",
    )
    rationale = models.TextField(blank=True, default="")
    editorial_status = models.CharField(
        max_length=20,
        choices=EditorialStatus.choices,
        default=EditorialStatus.DRAFT,
    )
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_knowledge_relations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("source_id", "relation_type", "target_id")
        constraints = [
            models.CheckConstraint(
                check=~Q(source=F("target")),
                name="iatrain_relation_distinct_nodes",
            ),
            models.UniqueConstraint(
                fields=("source", "target", "relation_type"),
                name="iatrain_relation_uniq_edge",
            ),
        ]
        indexes = [
            models.Index(
                fields=("source", "relation_type", "editorial_status"),
                name="iatrain_rel_source_idx",
            ),
            models.Index(fields=("target", "editorial_status"), name="iatrain_rel_target_idx"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.source_id and self.source_id == self.target_id:
            errors["target"] = "Una relació de coneixement no pot apuntar al mateix concepte."
        if not self.relation_type.strip():
            errors["relation_type"] = "La relació ha de tenir un tipus."
        if (
            self.editorial_status == self.EditorialStatus.VALIDATED
            and self.source_id
            and self.target_id
            and (
                self.source.editorial_status == KnowledgeConcept.EditorialStatus.RETIRED
                or self.target.editorial_status == KnowledgeConcept.EditorialStatus.RETIRED
            )
        ):
            errors["editorial_status"] = "Una relació validada no pot connectar conceptes retirats."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.source} —{self.relation_type}→ {self.target}"


class AthleteObservation(models.Model):
    """A narrative, versionable assertion about an athlete at a point in time."""

    class Category(models.TextChoices):
        COMPETENCY = "competency", "Competència"
        LEARNING = "learning", "Aprenentatge"
        STRENGTH = "strength", "Fortalesa"
        DIFFICULTY = "difficulty", "Dificultat"
        FEAR_BLOCK = "fear_block", "Por o bloqueig"
        LIMITATION = "limitation", "Limitació"
        NOTE = "note", "Nota"

    class Status(models.TextChoices):
        OBSERVED = "observed", "Observat"
        IN_PROGRESS = "in_progress", "En progrés"
        STABLE = "stable", "Estable"
        NO_LONGER_CURRENT = "no_longer_current", "No vigent"

    athlete = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="training_observations",
    )
    training_context = models.ForeignKey(
        TrainingContext,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="observations",
    )
    concept = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="athlete_observations",
    )
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.NOTE)
    narrative = models.TextField()
    evidence = models.TextField(
        blank=True,
        default="",
        help_text="Fets observables que sostenen la nota; no és una justificació generada automàticament.",
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.OBSERVED)
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
        help_text="Confiança entre 0 i 1; deixa-la buida si no es pot estimar honestament.",
    )
    intensity = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=(MinValueValidator(1), MaxValueValidator(5)),
        help_text="Intensitat opcional entre 1 i 5.",
    )
    observed_at = models.DateTimeField(default=timezone.now)
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_athlete_observations",
    )
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="superseded_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-observed_at", "-id")
        constraints = [
            models.CheckConstraint(
                check=Q(confidence__isnull=True) | (Q(confidence__gte=0) & Q(confidence__lte=1)),
                name="iatrain_obs_confidence_valid",
            ),
            models.CheckConstraint(
                check=Q(intensity__isnull=True) | (Q(intensity__gte=1) & Q(intensity__lte=5)),
                name="iatrain_obs_intensity_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("athlete", "status", "observed_at"), name="iatrain_obs_athlete_idx"),
            models.Index(fields=("training_context", "observed_at"), name="iatrain_obs_context_idx"),
            models.Index(fields=("concept", "category"), name="iatrain_obs_concept_idx"),
            models.Index(fields=("authored_by", "observed_at"), name="iatrain_obs_author_idx"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not self.narrative.strip():
            errors["narrative"] = "L'observació ha de contenir una descripció narrativa."
        if self.training_context_id and self.athlete_id:
            if not self.training_context.athletes.filter(pk=self.athlete_id).exists():
                errors["training_context"] = "El gimnasta no està associat a aquest context."
        if self.training_context_id and self.concept_id:
            context_scope = self.training_context.discipline.strip().lower()
            concept_scope = self.concept.discipline.strip().lower()
            if context_scope != concept_scope and "general" not in {context_scope, concept_scope}:
                errors["concept"] = "El concepte i el context han de compartir disciplina o àmbit general."
        if self.supersedes_id:
            if self.pk and self.supersedes_id == self.pk:
                errors["supersedes"] = "Una observació no es pot substituir a si mateixa."
            elif self.athlete_id and self.supersedes.athlete_id != self.athlete_id:
                errors["supersedes"] = "Una versió només pot substituir una observació del mateix gimnasta."
            elif self.observed_at and self.supersedes.observed_at > self.observed_at:
                errors["observed_at"] = "La nova versió no pot ser anterior a l'observació substituïda."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.athlete} · {self.get_category_display()} · {self.observed_at:%Y-%m-%d}"

