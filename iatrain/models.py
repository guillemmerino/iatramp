from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import Organization, Person


def validate_extracted_facts(value):
    """Validate the stable envelope used for facts extracted from natural language."""
    if not isinstance(value, list):
        raise ValidationError("Els fets extrets han de ser una llista.")
    allowed_statuses = {"unconfirmed", "confirmed", "rejected", "superseded"}
    for index, fact in enumerate(value):
        if not isinstance(fact, dict):
            raise ValidationError(f"El fet extret {index + 1} ha de ser un objecte.")
        if not isinstance(fact.get("key"), str) or not fact["key"].strip():
            raise ValidationError(f"El fet extret {index + 1} necessita una clau textual.")
        status = fact.get("status", "unconfirmed")
        if status not in allowed_statuses:
            raise ValidationError(f"El fet extret {index + 1} té un estat desconegut.")
        source = fact.get("source")
        if source is not None and not isinstance(source, str):
            raise ValidationError(f"La font del fet extret {index + 1} ha de ser textual.")
        confidence = fact.get("confidence")
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise ValidationError(
                f"La confiança del fet extret {index + 1} ha d'estar entre 0 i 1."
            )


class AthleteProfile(models.Model):
    person = models.OneToOneField(
        Person,
        on_delete=models.CASCADE,
        related_name="athlete_profile",
    )
    settings = models.JSONField(
        blank=True,
        default=dict,
        help_text="Configuració pròpia del mode gimnasta; només dades petites i estructurades.",
    )
    extracted_facts = models.JSONField(
        blank=True,
        default=list,
        validators=(validate_extracted_facts,),
        help_text=(
            "Fets extrets del llenguatge natural, amb font, confiança i estat; "
            "no substitueixen els camps de domini confirmats."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("person__last_name", "person__first_name", "id")

    def clean(self):
        super().clean()
        if not isinstance(self.settings, dict):
            raise ValidationError({"settings": "La configuració ha de ser un objecte JSON."})

    def __str__(self):
        return self.person.display_name


class CoachProfile(models.Model):
    person = models.OneToOneField(
        Person,
        on_delete=models.CASCADE,
        related_name="coach_profile",
    )
    settings = models.JSONField(
        blank=True,
        default=dict,
        help_text="Configuració pròpia del mode entrenador; només dades petites i estructurades.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("person__last_name", "person__first_name", "id")

    def clean(self):
        super().clean()
        if not isinstance(self.settings, dict):
            raise ValidationError({"settings": "La configuració ha de ser un objecte JSON."})

    def __str__(self):
        return self.person.display_name


class CoachAthleteRelation(models.Model):
    class Function(models.TextChoices):
        PRIMARY_COACH = "primary", "Entrenador/a principal"
        ASSISTANT_COACH = "assistant", "Entrenador/a assistent"
        PHYSICAL_TRAINER = "physical", "Preparació física"
        CHOREOGRAPHER = "choreographer", "Coreografia"
        OTHER = "other", "Altres"

    coach_profile = models.ForeignKey(
        CoachProfile,
        on_delete=models.CASCADE,
        related_name="athlete_relations",
    )
    athlete_profile = models.ForeignKey(
        AthleteProfile,
        on_delete=models.CASCADE,
        related_name="coach_relations",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="training_relationships",
        help_text="Organització en què s'aplica la relació; buit si és global.",
    )
    function = models.CharField(
        max_length=20,
        choices=Function.choices,
        default=Function.PRIMARY_COACH,
    )
    can_view_profile = models.BooleanField(default=True)
    can_view_training = models.BooleanField(default=True)
    can_edit_training = models.BooleanField(default=False)
    can_view_health_data = models.BooleanField(
        default=False,
        help_text="Permís sensible que s'ha de concedir explícitament.",
    )
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("athlete_profile_id", "coach_profile_id", "function")
        constraints = [
            models.CheckConstraint(
                check=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="iatrain_relation_dates_valid",
            ),
            models.CheckConstraint(
                check=Q(can_edit_training=False) | Q(can_view_training=True),
                name="iatrain_relation_edit_view",
            ),
            models.CheckConstraint(
                check=Q(can_view_health_data=False) | Q(can_view_profile=True),
                name="iatrain_relation_health_profile",
            ),
            models.UniqueConstraint(
                fields=("coach_profile", "athlete_profile", "organization", "function"),
                condition=Q(organization__isnull=False),
                name="iatrain_relation_uniq_context",
            ),
            models.UniqueConstraint(
                fields=("coach_profile", "athlete_profile", "function"),
                condition=Q(organization__isnull=True),
                name="iatrain_relation_uniq_global",
            ),
        ]
        indexes = [
            models.Index(
                fields=("coach_profile", "is_active"),
                name="iatrain_rel_coach_idx",
            ),
            models.Index(
                fields=("athlete_profile", "is_active"),
                name="iatrain_rel_athlete_idx",
            ),
            models.Index(
                fields=("organization", "is_active"),
                name="iatrain_rel_org_idx",
            ),
        ]

    @property
    def coach(self):
        return self.coach_profile.person

    @property
    def athlete(self):
        return self.athlete_profile.person

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.coach_profile_id
            and self.athlete_profile_id
            and self.coach_profile.person_id == self.athlete_profile.person_id
        ):
            errors["athlete_profile"] = "Una persona no pot ser entrenadora de si mateixa."
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "La data de fi no pot ser anterior a la d'inici."
        if self.can_edit_training and not self.can_view_training:
            errors["can_edit_training"] = "Editar entrenaments requereix poder-los consultar."
        if self.can_view_health_data and not self.can_view_profile:
            errors["can_view_health_data"] = "Consultar dades de salut requereix accés al perfil."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.coach} → {self.athlete} ({self.get_function_display()})"


class TrainingGroup(models.Model):
    """A stable roster of athletes who usually train together in an organization."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="training_groups",
    )
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True, default="")
    athletes = models.ManyToManyField(
        AthleteProfile,
        through="TrainingGroupMembership",
        related_name="training_groups",
        blank=True,
    )
    managing_coaches = models.ManyToManyField(
        CoachProfile,
        related_name="managed_training_groups",
        blank=True,
        help_text="Entrenadors amb capacitat explícita per gestionar el grup.",
    )
    extracted_facts = models.JSONField(
        blank=True,
        default=list,
        validators=(validate_extracted_facts,),
        help_text=(
            "Fets encara no formalitzats sobre el grup, com horaris, material o objectius."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("organization__name", "name", "id")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "organization",
                name="iatrain_group_name_org_ci_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "is_active"),
                name="iatrain_group_org_active_idx",
            )
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "El grup necessita un nom."})

    def __str__(self):
        return f"{self.organization} · {self.name}"


class TrainingGroupMembership(models.Model):
    training_group = models.ForeignKey(
        TrainingGroup,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    athlete_profile = models.ForeignKey(
        AthleteProfile,
        on_delete=models.CASCADE,
        related_name="group_memberships",
    )
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("training_group_id", "athlete_profile_id", "-start_date", "id")
        constraints = [
            models.CheckConstraint(
                check=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="iatrain_group_membership_dates_valid",
            ),
            models.UniqueConstraint(
                fields=("training_group", "athlete_profile"),
                condition=Q(is_active=True),
                name="iatrain_group_member_unique_active",
            ),
        ]
        indexes = [
            models.Index(
                fields=("training_group", "is_active"),
                name="iatrain_grp_member_group_idx",
            ),
            models.Index(
                fields=("athlete_profile", "is_active"),
                name="iatrain_grp_member_ath_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                {"end_date": "La data de fi no pot ser anterior a la d'inici."}
            )

    def is_current(self, on_date=None):
        on_date = on_date or timezone.localdate()
        return (
            self.is_active
            and self.start_date <= on_date
            and (self.end_date is None or self.end_date >= on_date)
            and self.training_group.is_active
        )

    def __str__(self):
        return f"{self.athlete_profile} · {self.training_group}"


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
