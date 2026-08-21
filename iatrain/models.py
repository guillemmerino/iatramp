import re
import unicodedata

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import Person
from organizations.models import Organization


def normalize_label(value):
    """Normalize human labels without losing their display casing."""
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def normalize_vocabulary_token(value):
    """Return the canonical storage form for extensible vocabulary keys."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"[\s-]+", "_", normalized)


def validated_content_changed(instance, field_names):
    """Detect silent edits to content that is still marked as validated."""
    if not instance.pk or instance.editorial_status != "validated":
        return False
    previous = type(instance).objects.filter(pk=instance.pk).values(
        "editorial_status", *field_names
    ).first()
    if not previous or previous["editorial_status"] != "validated":
        return False
    return any(previous[field] != getattr(instance, field) for field in field_names)


def validated_concept_attributes_changed(instance):
    """Allow append-only legacy provenance while protecting validated semantics."""
    if not instance.pk or instance.editorial_status != "validated":
        return False
    previous = type(instance).objects.filter(pk=instance.pk).values(
        "editorial_status", "attributes"
    ).first()
    if not previous or previous["editorial_status"] != "validated":
        return False
    old_attributes = dict(previous["attributes"] or {})
    new_attributes = dict(instance.attributes or {})
    old_sources = old_attributes.pop("legacy_sources", [])
    new_sources = new_attributes.pop("legacy_sources", [])
    if old_attributes != new_attributes:
        return True
    return any(source not in new_sources for source in old_sources)


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


def validate_catalog_equipment_codes(value):
    """Validate the optional bridge from a gym inventory row to catalog codes."""
    if not isinstance(value, list):
        raise ValidationError("Els codis de material han de ser una llista.")
    normalized = []
    for code in value:
        if not isinstance(code, str) or not normalize_vocabulary_token(code):
            raise ValidationError("Cada codi de material ha de ser textual i no buit.")
        normalized.append(normalize_vocabulary_token(code))
    if len(normalized) != len(set(normalized)):
        raise ValidationError("Els codis de material no es poden repetir.")


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


class Gym(models.Model):
    """A training venue that can be shared by one or more organizations."""

    name = models.CharField(max_length=180)
    location = models.CharField(max_length=240, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    organizations = models.ManyToManyField(
        Organization,
        through="GymOrganization",
        related_name="training_gyms",
        blank=True,
    )
    created_by = models.ForeignKey(
        CoachProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_gyms",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "location", "id")
        indexes = [models.Index(fields=("is_active", "name"), name="iatrain_gym_active_idx")]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        self.location = self.location.strip()
        if not self.name:
            raise ValidationError({"name": "El gimnàs necessita un nom."})

    def __str__(self):
        return self.name


class GymOrganization(models.Model):
    """Explicitly grants an organization access to a gym."""

    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="organization_links")
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="gym_links",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("organization__name", "gym__name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("gym", "organization"),
                name="iatrain_gym_org_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "is_active"),
                name="iatrain_gym_org_active_idx",
            )
        ]

    def __str__(self):
        return f"{self.gym} · {self.organization}"


class GymEquipment(models.Model):
    """A structured inventory row consumed by the training engine."""

    class EquipmentType(models.TextChoices):
        TRAMPOLINE = "trampoline", "Trampolí"
        DOUBLE_MINI = "double_mini", "Doble minitrampolí"
        TUMBLING_TRACK = "tumbling_track", "Pista de tumbling"
        MAT = "mat", "Matalàs"
        SPOTTING_PLATFORM = "spotting_platform", "Plataforma de seguretat"
        HARNESS = "harness", "Cinturó o arnès"
        CONDITIONING = "conditioning", "Preparació física"
        OTHER = "other", "Altres"

    class Availability(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        LIMITED = "limited", "Ús limitat"
        MAINTENANCE = "maintenance", "En manteniment"
        UNAVAILABLE = "unavailable", "No disponible"

    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name="equipment")
    name = models.CharField(max_length=180)
    equipment_type = models.CharField(
        max_length=30,
        choices=EquipmentType.choices,
        default=EquipmentType.OTHER,
    )
    quantity = models.PositiveSmallIntegerField(
        default=1,
        validators=(MinValueValidator(1),),
    )
    availability = models.CharField(
        max_length=20,
        choices=Availability.choices,
        default=Availability.AVAILABLE,
    )
    notes = models.TextField(blank=True, default="")
    catalog_equipment_codes = models.JSONField(
        blank=True,
        default=list,
        validators=(validate_catalog_equipment_codes,),
        help_text=(
            "Codis del material dels catàlegs d'exercicis equivalent a aquest inventari. "
            "El motor també intenta resoldre equivalències pel nom."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("gym_id", "equipment_type", "name", "id")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "gym",
                name="iatrain_gym_equipment_name_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("gym", "availability"),
                name="iatrain_gym_equipment_idx",
            )
        ]

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "El material necessita un nom."})

    def __str__(self):
        return f"{self.gym} · {self.name}"


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
        BODY_POSITION = "body_position"
        CONTACT_POSITION = "contact_position"
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
    last_validated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_knowledge_concepts",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
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
        self.name = normalize_label(self.name)
        self.kind = normalize_vocabulary_token(self.kind)
        self.discipline = normalize_vocabulary_token(self.discipline)
        errors = {}
        if not self.name.strip():
            errors["name"] = "El concepte ha de tenir un nom."
        if not self.kind.strip():
            errors["kind"] = "El concepte ha de tenir un tipus."
        if not self.discipline.strip():
            errors["discipline"] = "L'àmbit o disciplina no pot quedar buit."
        if not isinstance(self.attributes, dict):
            errors["attributes"] = "Els atributs han de ser un objecte JSON."
        if validated_content_changed(
            self,
            ("name", "description", "kind", "discipline"),
        ) or validated_concept_attributes_changed(self):
            errors["editorial_status"] = (
                "Reobre el concepte com a esborrany abans de modificar contingut validat."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Els conceptes professionals no s'eliminen; retira'ls mitjançant el servei editorial."
        )


class KnowledgeRelation(models.Model):
    """A directed, editorially governed edge in the professional graph."""

    class RelationType:
        REQUIRES = "requires"
        PROGRESSES_TO = "progresses_to"
        HAS_DEFINING_POSITION = "has_defining_position"
        STARTS_FROM_CONTACT = "starts_from_contact"
        ENDS_IN_CONTACT = "ends_in_contact"
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
    last_validated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_knowledge_relations",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
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
        self.relation_type = normalize_vocabulary_token(self.relation_type)
        errors = {}
        if self.source_id and self.source_id == self.target_id:
            errors["target"] = "Una relació de coneixement no pot apuntar al mateix concepte."
        if not self.relation_type.strip():
            errors["relation_type"] = "La relació ha de tenir un tipus."
        endpoint_values = {}
        endpoint_values_complete = False
        if self.source_id and self.target_id:
            endpoint_values = {
                row["id"]: row
                for row in KnowledgeConcept.objects.filter(
                    pk__in=(self.source_id, self.target_id)
                ).values("id", "kind", "editorial_status")
            }
            endpoint_values_complete = len(endpoint_values) == len(
                {self.source_id, self.target_id}
            )
        if (
            self.editorial_status == self.EditorialStatus.VALIDATED
            and endpoint_values_complete
        ):
            if any(
                endpoint_values[concept_id]["editorial_status"]
                != KnowledgeConcept.EditorialStatus.VALIDATED
                for concept_id in (self.source_id, self.target_id)
            ):
                errors["editorial_status"] = (
                    "Una relació validada només pot connectar conceptes validats."
                )
        known_domains = {
            self.RelationType.HAS_DEFINING_POSITION: (
                KnowledgeConcept.Kind.SKILL,
                KnowledgeConcept.Kind.BODY_POSITION,
            ),
            self.RelationType.STARTS_FROM_CONTACT: (
                KnowledgeConcept.Kind.SKILL,
                KnowledgeConcept.Kind.CONTACT_POSITION,
            ),
            self.RelationType.ENDS_IN_CONTACT: (
                KnowledgeConcept.Kind.SKILL,
                KnowledgeConcept.Kind.CONTACT_POSITION,
            ),
        }
        expected_kinds = known_domains.get(self.relation_type)
        if expected_kinds and endpoint_values_complete:
            actual_kinds = (
                endpoint_values[self.source_id]["kind"],
                endpoint_values[self.target_id]["kind"],
            )
            if actual_kinds != expected_kinds:
                errors["relation_type"] = (
                    f"{self.relation_type} requereix origen {expected_kinds[0]} "
                    f"i destí {expected_kinds[1]}."
                )
        if validated_content_changed(
            self,
            ("source_id", "target_id", "relation_type", "rationale"),
        ):
            errors["editorial_status"] = (
                "Reobre la relació com a esborrany abans de modificar contingut validat."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.source} —{self.relation_type}→ {self.target}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Les relacions professionals no s'eliminen; retira-les mitjançant el servei editorial."
        )


class KnowledgeEditorialEvent(models.Model):
    """Durable audit event for editorial transitions across knowledge models."""

    target_model = models.CharField(max_length=100)
    target_id = models.PositiveBigIntegerField()
    target_repr = models.CharField(max_length=255)
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    decided_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="knowledge_editorial_decisions",
    )
    reason = models.TextField(blank=True, default="")
    snapshot = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("target_model", "target_id", "created_at"),
                name="iatrain_editorial_target_idx",
            ),
            models.Index(
                fields=("decided_by", "created_at"),
                name="iatrain_editorial_actor_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.target_model = normalize_label(self.target_model).casefold()
        self.target_repr = normalize_label(self.target_repr)
        if not isinstance(self.snapshot, dict):
            raise ValidationError({"snapshot": "La captura editorial ha de ser un objecte JSON."})

    def __str__(self):
        return f"{self.target_repr}: {self.from_status} → {self.to_status}"


class ElementRotation(models.Model):
    """Canonical transverse rotation and ordered longitudinal components for a skill."""

    class Direction(models.TextChoices):
        UNKNOWN = "unknown", "No resolta"
        NONE = "none", "Sense rotació transversal"
        FORWARD = "forward", "Endavant"
        BACKWARD = "backward", "Enrere"

    element = models.OneToOneField(
        KnowledgeConcept,
        on_delete=models.PROTECT,
        related_name="rotation_profile",
    )
    transverse_quarters = models.PositiveSmallIntegerField()
    transverse_direction = models.CharField(
        max_length=20,
        choices=Direction.choices,
        default=Direction.UNKNOWN,
    )
    editorial_status = models.CharField(
        max_length=20,
        choices=KnowledgeConcept.EditorialStatus.choices,
        default=KnowledgeConcept.EditorialStatus.DRAFT,
    )
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_element_rotations",
    )
    last_validated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_element_rotations",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
    provenance = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("element_id",)
        indexes = [
            models.Index(
                fields=("editorial_status", "transverse_quarters"),
                name="iatrain_rotation_scope_idx",
            )
        ]

    @property
    def expected_segment_count(self):
        return max(1, (self.transverse_quarters + 3) // 4)

    def clean(self):
        super().clean()
        errors = {}
        if self.element_id and self.element.kind != KnowledgeConcept.Kind.SKILL:
            errors["element"] = "El perfil de rotació només es pot associar a un element."
        if self.transverse_quarters == 0 and self.transverse_direction not in {
            self.Direction.NONE,
            self.Direction.UNKNOWN,
        }:
            errors["transverse_direction"] = (
                "Un element sense quarts transversals no pot indicar direcció endavant o enrere."
            )
        if self.transverse_quarters > 0 and self.transverse_direction == self.Direction.NONE:
            errors["transverse_direction"] = (
                "Una rotació transversal positiva necessita direcció o ha de quedar no resolta."
            )
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if (
            self.editorial_status == KnowledgeConcept.EditorialStatus.VALIDATED
            and self.element_id
            and self.element.editorial_status != KnowledgeConcept.EditorialStatus.VALIDATED
        ):
            errors["editorial_status"] = (
                "Un perfil de rotació validat necessita un element validat."
            )
        if validated_content_changed(
            self,
            ("element_id", "transverse_quarters", "transverse_direction", "provenance"),
        ):
            errors["editorial_status"] = (
                "Reobre el perfil com a esborrany abans de modificar contingut validat."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.element} · {self.transverse_quarters} quarts"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Els perfils de rotació no s'eliminen; retira'ls mitjançant el servei editorial."
        )


class ElementRotationSegment(models.Model):
    """Longitudinal half-turns assigned to one ordered somersault segment."""

    rotation = models.ForeignKey(
        ElementRotation,
        on_delete=models.CASCADE,
        related_name="segments",
    )
    sequence_index = models.PositiveSmallIntegerField()
    longitudinal_half_turns = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("rotation_id", "sequence_index")
        constraints = [
            models.CheckConstraint(
                check=Q(sequence_index__gte=1),
                name="iatrain_rotation_segment_index",
            ),
            models.UniqueConstraint(
                fields=("rotation", "sequence_index"),
                name="iatrain_rotation_segment_uniq",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.rotation_id
            and self.rotation.editorial_status == KnowledgeConcept.EditorialStatus.VALIDATED
        ):
            previous = type(self).objects.filter(pk=self.pk).values(
                "sequence_index", "longitudinal_half_turns"
            ).first()
            if previous is None or any(
                previous[field] != getattr(self, field)
                for field in ("sequence_index", "longitudinal_half_turns")
            ):
                raise ValidationError(
                    "Reobre el perfil de rotació abans de modificar-ne els segments."
                )
        if self.rotation_id and self.sequence_index > self.rotation.expected_segment_count:
            raise ValidationError(
                {
                    "sequence_index": (
                        "L'índex supera els segments esperats pels quarts transversals."
                    )
                }
            )

    def __str__(self):
        return (
            f"{self.rotation.element} · segment {self.sequence_index}: "
            f"{self.longitudinal_half_turns} mig girs"
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ElementNotation(models.Model):
    """Raw and normalized notation tied to an element and optionally to a parsed profile."""

    class ParseStatus(models.TextChoices):
        PARSED = "parsed", "Interpretada"
        AMBIGUOUS = "ambiguous", "Ambigua"
        INVALID = "invalid", "No vàlida"

    class ResolutionSource(models.TextChoices):
        EXPLICIT = "explicit", "Explícita"
        INFERRED = "inferred", "Inferida"
        UNKNOWN = "unknown", "No resolta"

    element = models.ForeignKey(
        KnowledgeConcept,
        on_delete=models.PROTECT,
        related_name="rotation_notations",
    )
    rotation = models.ForeignKey(
        ElementRotation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="notations",
    )
    scheme = models.CharField(max_length=40, default="fig_numeric")
    scheme_version = models.CharField(max_length=40, blank=True, default="legacy")
    raw_notation = models.CharField(max_length=80)
    normalized_notation = models.CharField(max_length=80, blank=True, default="")
    parse_status = models.CharField(
        max_length=20,
        choices=ParseStatus.choices,
        default=ParseStatus.PARSED,
    )
    is_abbreviated = models.BooleanField(default=False)
    direction_source = models.CharField(
        max_length=20,
        choices=ResolutionSource.choices,
        default=ResolutionSource.UNKNOWN,
    )
    position_source = models.CharField(
        max_length=20,
        choices=ResolutionSource.choices,
        default=ResolutionSource.UNKNOWN,
    )
    position_symbol = models.CharField(max_length=1, blank=True, default="")
    parse_details = models.JSONField(blank=True, default=dict)
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_element_notations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("element_id", "scheme", "raw_notation", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("element", "scheme", "raw_notation"),
                name="iatrain_element_notation_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("scheme", "parse_status"),
                name="iatrain_notation_status_idx",
            )
        ]

    def clean(self):
        super().clean()
        self.scheme = normalize_vocabulary_token(self.scheme)
        self.scheme_version = normalize_vocabulary_token(self.scheme_version)
        errors = {}
        self.raw_notation = self.raw_notation.strip()
        if self.element_id and self.element.kind != KnowledgeConcept.Kind.SKILL:
            errors["element"] = "La notació només es pot associar a un element."
        if not self.raw_notation:
            errors["raw_notation"] = "La notació original no pot quedar buida."
        if self.rotation_id and self.element_id and self.rotation.element_id != self.element_id:
            errors["rotation"] = "El perfil de rotació i la notació han de ser del mateix element."
        if self.parse_status == self.ParseStatus.PARSED and not self.rotation_id:
            errors["rotation"] = "Una notació interpretada necessita un perfil de rotació."
        if self.position_symbol not in {"", "o", "<", "/"}:
            errors["position_symbol"] = "Símbol de posició desconegut."
        if not isinstance(self.parse_details, dict):
            errors["parse_details"] = "Els detalls d'interpretació han de ser un objecte JSON."
        if (
            self.rotation_id
            and self.rotation.editorial_status == KnowledgeConcept.EditorialStatus.VALIDATED
        ):
            protected_fields = (
                "element_id",
                "rotation_id",
                "scheme",
                "scheme_version",
                "raw_notation",
                "normalized_notation",
                "parse_status",
                "is_abbreviated",
                "direction_source",
                "position_source",
                "position_symbol",
                "parse_details",
            )
            previous = type(self).objects.filter(pk=self.pk).values(*protected_fields).first()
            if previous is None or any(
                previous[field] != getattr(self, field) for field in protected_fields
            ):
                errors["rotation"] = (
                    "Reobre el perfil de rotació abans de modificar-ne les notacions."
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.element} · {self.raw_notation}"

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Les notacions professionals es conserven com a evidència i no s'eliminen."
        )


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
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="athlete_observations",
        help_text="Abast de privacitat; buit només per a observacions personals globals.",
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
        on_delete=models.PROTECT,
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
        if self.training_context_id and self.organization_id:
            if self.training_context.organization_id != self.organization_id:
                errors["organization"] = "L'organització ha de coincidir amb el context."
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


# Training is split by domain internally while preserving the conventional
# ``iatrain.models`` import surface used by Django and the rest of the project.
from .training.models import (  # noqa: E402,F401
    BlockParticipantAssignment,
    PhysicalExercisePrescription,
    SessionAttendance,
    SessionGoal,
    SessionItemAlternative,
    SessionItemAthleteAdjustment,
    SessionParticipantPlan,
    TrainingBlock,
    BlockGenerationRun,
    TrainingItemResult,
    TrainingSession,
    TrainingSessionExecution,
    TrainingSessionItem,
    TrainingSessionRevision,
)

from .athletes.models import (  # noqa: E402,F401
    AthleteCondition,
    AthleteInsight,
    AthleteInsightEvidence,
    AthleteMeasurement,
    AthleteSportProfile,
)
