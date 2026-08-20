from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import Person
from iatrain_motion.models import MotionConcept, normalize_code
from organizations.models import Organization


class CleanOnSaveModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class AthleteSportProfile(CleanOnSaveModel):
    """Stable sporting context without turning the athlete into one rigid form."""

    class Discipline(models.TextChoices):
        TRAMPOLINE = "trampoline", "Trampolí"
        DMT = "dmt", "Doble minitrampolí"
        TUMBLING = "tumbling", "Tumbling"
        GENERAL = "general", "Preparació general"

    class Laterality(models.TextChoices):
        UNKNOWN = "unknown", "No determinada"
        RIGHT = "right", "Dreta"
        LEFT = "left", "Esquerra"
        MIXED = "mixed", "Mixta"

    athlete_profile = models.ForeignKey(
        "iatrain.AthleteProfile",
        on_delete=models.PROTECT,
        related_name="sport_profiles",
    )
    discipline = models.CharField(max_length=20, choices=Discipline.choices)
    level_code = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="Vocabulari extensible de nivell; no pressuposa una escala universal.",
    )
    training_started_on = models.DateField(null=True, blank=True)
    preferred_laterality = models.CharField(
        max_length=20, choices=Laterality.choices, default=Laterality.UNKNOWN
    )
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="updated_athlete_sport_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("athlete_profile_id", "discipline")
        constraints = [
            models.UniqueConstraint(
                fields=("athlete_profile", "discipline"),
                name="iatrain_athlete_sport_profile_uniq",
            )
        ]

    def clean(self):
        super().clean()
        self.level_code = normalize_code(self.level_code) if self.level_code else ""
        if self.training_started_on and self.training_started_on > timezone.localdate():
            raise ValidationError(
                {"training_started_on": "L'inici esportiu no pot ser en el futur."}
            )

    def __str__(self):
        return f"{self.athlete_profile} · {self.get_discipline_display()}"

    @property
    def level_label(self):
        return self.level_code.replace("_", " ").strip().capitalize()


class AthleteMeasurement(CleanOnSaveModel):
    """A dated objective or reported value, preserved as a time series."""

    class Domain(models.TextChoices):
        ANTHROPOMETRY = "anthropometry", "Antropometria"
        STRENGTH = "strength", "Força"
        POWER = "power", "Potència"
        MOBILITY = "mobility", "Mobilitat"
        MOTOR_CONTROL = "motor_control", "Control motor"
        ENDURANCE = "endurance", "Resistència"
        RECOVERY = "recovery", "Recuperació"
        WORKLOAD = "workload", "Càrrega"
        OTHER = "other", "Altres"

    class Side(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "No aplicable"
        BILATERAL = "bilateral", "Bilateral"
        RIGHT = "right", "Dreta"
        LEFT = "left", "Esquerra"

    class Source(models.TextChoices):
        ASSESSMENT = "assessment", "Valoració"
        DEVICE = "device", "Dispositiu"
        TRAINING_RESULT = "training_result", "Resultat d'entrenament"
        ATHLETE_REPORT = "athlete_report", "Informació del gimnasta"
        IMPORTED = "imported", "Importada"

    class Status(models.TextChoices):
        VALID = "valid", "Vàlida"
        INVALIDATED = "invalidated", "Invalidada"

    athlete_profile = models.ForeignKey(
        "iatrain.AthleteProfile",
        on_delete=models.PROTECT,
        related_name="measurements",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="athlete_measurements",
    )
    domain = models.CharField(max_length=30, choices=Domain.choices)
    metric_code = models.CharField(max_length=100)
    metric_label = models.CharField(max_length=180)
    value = models.DecimalField(max_digits=12, decimal_places=4)
    unit = models.CharField(max_length=40)
    side = models.CharField(
        max_length=20, choices=Side.choices, default=Side.NOT_APPLICABLE
    )
    protocol = models.TextField(blank=True, default="")
    source = models.CharField(max_length=30, choices=Source.choices)
    uncertainty = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        validators=(MinValueValidator(0),),
    )
    measured_at = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.VALID)
    notes = models.TextField(blank=True, default="")
    recorded_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="recorded_athlete_measurements",
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
        ordering = ("-measured_at", "-id")
        constraints = [
            models.CheckConstraint(
                check=~Q(supersedes=F("id")), name="iatrain_measure_no_self_supersede"
            ),
        ]
        indexes = [
            models.Index(
                fields=("athlete_profile", "metric_code", "measured_at"),
                name="iatrain_measure_metric_idx",
            ),
            models.Index(
                fields=("organization", "measured_at"),
                name="iatrain_measure_org_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        self.metric_code = normalize_code(self.metric_code)
        self.metric_label = " ".join(str(self.metric_label or "").split())
        self.unit = str(self.unit or "").strip().casefold()
        if not self.metric_code:
            errors["metric_code"] = "La mesura necessita un codi estable."
        if not self.metric_label:
            errors["metric_label"] = "La mesura necessita un nom entenedor."
        if not self.unit:
            errors["unit"] = "La mesura necessita una unitat explícita."
        if self.valid_until and self.measured_at and self.valid_until < self.measured_at:
            errors["valid_until"] = "La vigència no pot acabar abans de la mesura."
        if self.supersedes_id:
            if self.pk and self.supersedes_id == self.pk:
                errors["supersedes"] = "Una mesura no es pot corregir a si mateixa."
            elif self.supersedes.athlete_profile_id != self.athlete_profile_id:
                errors["supersedes"] = "Només es pot corregir una mesura del mateix gimnasta."
            elif self.supersedes.metric_code != self.metric_code:
                errors["metric_code"] = "Una correcció ha de conservar la mateixa mètrica."
            elif self.supersedes.side != self.side:
                errors["side"] = "Una correcció ha de conservar la mateixa lateralitat."
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if self._state.adding and self.status != self.Status.VALID:
            errors["status"] = "Una mesura nova sempre entra com a vàlida."
        if previous:
            governed_fields = (
                "athlete_profile_id",
                "organization_id",
                "domain",
                "metric_code",
                "metric_label",
                "value",
                "unit",
                "side",
                "protocol",
                "source",
                "uncertainty",
                "measured_at",
                "valid_until",
                "notes",
                "recorded_by_id",
                "supersedes_id",
            )
            if any(getattr(previous, field) != getattr(self, field) for field in governed_fields):
                errors["status"] = "Corregeix la mesura creant-ne una de nova."
            if previous.status == self.Status.INVALIDATED and self.status != previous.status:
                errors["status"] = "Una mesura invalidada no es pot reactivar."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        raise ValidationError("Les mesures s'invaliden o es corregeixen; no s'eliminen.")

    def __str__(self):
        return f"{self.athlete_profile} · {self.metric_label}: {self.value} {self.unit}"


class AthleteCondition(CleanOnSaveModel):
    """A temporary condition that may alter training selection, not a diagnosis."""

    class Category(models.TextChoices):
        PAIN = "pain", "Dolor"
        DISCOMFORT = "discomfort", "Molèstia"
        INJURY = "injury", "Lesió comunicada"
        MEDICAL_RESTRICTION = "medical_restriction", "Restricció mèdica"
        LOAD_TOLERANCE = "load_tolerance", "Tolerància de càrrega"
        READINESS = "readiness", "Disponibilitat"
        OTHER = "other", "Altres"

    class Laterality(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "No aplicable"
        BILATERAL = "bilateral", "Bilateral"
        RIGHT = "right", "Dreta"
        LEFT = "left", "Esquerra"

    class TrainingImpact(models.TextChoices):
        NONE = "none", "Sense impacte declarat"
        MONITOR = "monitor", "Monitorar"
        MODIFY = "modify", "Modificar"
        AVOID = "avoid", "Evitar"
        STOP = "stop", "No entrenar"

    class Source(models.TextChoices):
        ATHLETE_REPORT = "athlete_report", "Informació del gimnasta"
        COACH_OBSERVATION = "coach_observation", "Observació de l'entrenador"
        SESSION_RESPONSE = "session_response", "Resposta durant una sessió"
        CLINICAL_DOCUMENT = "clinical_document", "Document clínic aportat"
        IMPORTED = "imported", "Importada"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Pendent de confirmació"
        CONFIRMED = "confirmed", "Confirmada"
        RESOLVED = "resolved", "Resolta"
        REJECTED = "rejected", "Descartada"
        SUPERSEDED = "superseded", "Substituïda"

    athlete_profile = models.ForeignKey(
        "iatrain.AthleteProfile",
        on_delete=models.PROTECT,
        related_name="conditions",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="athlete_conditions",
    )
    category = models.CharField(max_length=30, choices=Category.choices)
    title = models.CharField(max_length=180)
    narrative = models.TextField()
    evidence = models.TextField(blank=True, default="")
    body_region = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="athlete_conditions",
    )
    laterality = models.CharField(
        max_length=20, choices=Laterality.choices, default=Laterality.NOT_APPLICABLE
    )
    severity = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=(MinValueValidator(1), MaxValueValidator(5)),
    )
    training_impact = models.CharField(
        max_length=20, choices=TrainingImpact.choices, default=TrainingImpact.MONITOR
    )
    source = models.CharField(max_length=30, choices=Source.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="recorded_athlete_conditions",
    )
    confirmed_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="confirmed_athlete_conditions",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
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
        ordering = ("-started_at", "-id")
        constraints = [
            models.CheckConstraint(
                check=Q(severity__isnull=True)
                | (Q(severity__gte=1) & Q(severity__lte=5)),
                name="iatrain_condition_severity_valid",
            ),
            models.CheckConstraint(
                check=~Q(supersedes=F("id")), name="iatrain_condition_no_self_sup"
            ),
        ]
        indexes = [
            models.Index(
                fields=("athlete_profile", "status", "started_at"),
                name="iatrain_condition_current_idx",
            ),
            models.Index(
                fields=("organization", "status"), name="iatrain_condition_org_idx"
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        self.title = " ".join(str(self.title or "").split())
        if not self.title:
            errors["title"] = "La condició necessita un títol."
        if not self.narrative.strip():
            errors["narrative"] = "La condició necessita una descripció."
        if self.body_region_id and self.body_region.kind not in {
            MotionConcept.Kind.SEGMENT,
            MotionConcept.Kind.JOINT,
            MotionConcept.Kind.MUSCLE,
            MotionConcept.Kind.MUSCLE_GROUP,
        }:
            errors["body_region"] = "La regió ha de ser una estructura anatòmica."
        if self.ended_at and self.ended_at < self.started_at:
            errors["ended_at"] = "La condició no pot acabar abans de començar."
        if self.valid_until and self.valid_until < self.started_at:
            errors["valid_until"] = "La vigència no pot acabar abans de començar."
        if self.status == self.Status.CONFIRMED and not (
            self.confirmed_by_id and self.confirmed_at
        ):
            errors["confirmed_by"] = "Una condició confirmada necessita autoria i data."
        if self.status == self.Status.PROPOSED and (self.confirmed_by_id or self.confirmed_at):
            errors["confirmed_by"] = "Una proposta encara no pot tenir dades de confirmació."
        if self.status == self.Status.RESOLVED and not self.ended_at:
            errors["ended_at"] = "Una condició resolta necessita data de finalització."
        if self.supersedes_id:
            if self.pk and self.supersedes_id == self.pk:
                errors["supersedes"] = "Una condició no es pot substituir a si mateixa."
            elif self.supersedes.athlete_profile_id != self.athlete_profile_id:
                errors["supersedes"] = "Només es pot substituir una condició del mateix gimnasta."
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if self._state.adding and self.status != self.Status.PROPOSED:
            errors["status"] = "Una condició nova sempre entra pendent de confirmació."
        if previous and previous.status != self.Status.PROPOSED:
            governed_fields = (
                "athlete_profile_id",
                "organization_id",
                "category",
                "title",
                "narrative",
                "evidence",
                "body_region_id",
                "laterality",
                "severity",
                "training_impact",
                "source",
                "started_at",
                "valid_until",
                "recorded_by_id",
                "supersedes_id",
            )
            if any(getattr(previous, field) != getattr(self, field) for field in governed_fields):
                errors["status"] = "Una condició revisada no es pot reescriure."
        if previous and previous.status != self.status:
            allowed = {
                self.Status.PROPOSED: {self.Status.CONFIRMED, self.Status.REJECTED},
                self.Status.CONFIRMED: {self.Status.RESOLVED, self.Status.SUPERSEDED},
                self.Status.RESOLVED: set(),
                self.Status.REJECTED: set(),
                self.Status.SUPERSEDED: set(),
            }
            if self.status not in allowed.get(previous.status, set()):
                errors["status"] = "Aquesta transició de la condició no és vàlida."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        raise ValidationError("Les condicions es resolen o es descarten; no s'eliminen.")

    def __str__(self):
        return f"{self.athlete_profile} · {self.title}"


class AthleteInsight(CleanOnSaveModel):
    """An explainable interpretation; never silently promoted to an athlete fact."""

    class Kind(models.TextChoices):
        TREND = "trend", "Tendència"
        PROGRESS = "progress", "Progrés"
        TOLERANCE = "tolerance", "Tolerància"
        PREFERENCE = "preference", "Preferència"
        RISK_SIGNAL = "risk_signal", "Senyal de risc"
        HYPOTHESIS = "hypothesis", "Hipòtesi"
        DATA_GAP = "data_gap", "Manca d'informació"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposada"
        CONFIRMED = "confirmed", "Confirmada"
        REJECTED = "rejected", "Descartada"
        SUPERSEDED = "superseded", "Substituïda"
        EXPIRED = "expired", "Caducada"

    athlete_profile = models.ForeignKey(
        "iatrain.AthleteProfile",
        on_delete=models.PROTECT,
        related_name="insights",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="athlete_insights",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    statement = models.TextField()
    rationale = models.TextField()
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    evidence_window_start = models.DateTimeField(null=True, blank=True)
    evidence_window_end = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    model_name = models.CharField(max_length=120, blank=True, default="")
    triggered_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="triggered_athlete_insights",
    )
    confirmed_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="confirmed_athlete_insights",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("athlete_profile", "status", "kind"),
                name="iatrain_insight_current_idx",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not self.statement.strip():
            errors["statement"] = "La interpretació necessita una afirmació."
        if not self.rationale.strip():
            errors["rationale"] = "La interpretació ha d'explicar el raonament."
        if (
            self.evidence_window_start
            and self.evidence_window_end
            and self.evidence_window_end < self.evidence_window_start
        ):
            errors["evidence_window_end"] = "La finestra d'evidència no és coherent."
        if self.status == self.Status.CONFIRMED and not (
            self.confirmed_by_id and self.confirmed_at
        ):
            errors["confirmed_by"] = "Una interpretació confirmada necessita autoria i data."
        if self.status == self.Status.PROPOSED and (self.confirmed_by_id or self.confirmed_at):
            errors["confirmed_by"] = "Una proposta encara no pot tenir dades de confirmació."
        previous = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if self._state.adding and self.status != self.Status.PROPOSED:
            errors["status"] = "Una interpretació nova sempre entra com a proposta."
        if previous and previous.status != self.Status.PROPOSED:
            governed_fields = (
                "athlete_profile_id",
                "organization_id",
                "kind",
                "statement",
                "rationale",
                "confidence",
                "evidence_window_start",
                "evidence_window_end",
                "valid_until",
                "model_name",
                "triggered_by_id",
            )
            if any(getattr(previous, field) != getattr(self, field) for field in governed_fields):
                errors["status"] = "Una interpretació revisada no es pot reescriure."
        if previous and previous.status != self.status:
            allowed = {
                self.Status.PROPOSED: {self.Status.CONFIRMED, self.Status.REJECTED},
                self.Status.CONFIRMED: {self.Status.SUPERSEDED, self.Status.EXPIRED},
                self.Status.REJECTED: set(),
                self.Status.SUPERSEDED: set(),
                self.Status.EXPIRED: set(),
            }
            if self.status not in allowed.get(previous.status, set()):
                errors["status"] = "Aquesta transició de la interpretació no és vàlida."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        raise ValidationError("Les interpretacions es descarten o caduquen; no s'eliminen.")

    def __str__(self):
        return f"{self.athlete_profile} · {self.get_kind_display()}"


class AthleteInsightEvidence(CleanOnSaveModel):
    """A typed evidence edge supporting one insight."""

    insight = models.ForeignKey(
        AthleteInsight, on_delete=models.CASCADE, related_name="evidence_links"
    )
    observation = models.ForeignKey(
        "iatrain.AthleteObservation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="insight_evidence_links",
    )
    measurement = models.ForeignKey(
        AthleteMeasurement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="insight_evidence_links",
    )
    condition = models.ForeignKey(
        AthleteCondition,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="insight_evidence_links",
    )
    training_item_result = models.ForeignKey(
        "iatrain.TrainingItemResult",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="insight_evidence_links",
    )
    contribution = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("insight_id", "id")
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(
                        observation__isnull=False,
                        measurement__isnull=True,
                        condition__isnull=True,
                        training_item_result__isnull=True,
                    )
                    | Q(
                        observation__isnull=True,
                        measurement__isnull=False,
                        condition__isnull=True,
                        training_item_result__isnull=True,
                    )
                    | Q(
                        observation__isnull=True,
                        measurement__isnull=True,
                        condition__isnull=False,
                        training_item_result__isnull=True,
                    )
                    | Q(
                        observation__isnull=True,
                        measurement__isnull=True,
                        condition__isnull=True,
                        training_item_result__isnull=False,
                    )
                ),
                name="iatrain_insight_evidence_one_source",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        sources = [
            self.observation_id,
            self.measurement_id,
            self.condition_id,
            self.training_item_result_id,
        ]
        if sum(value is not None for value in sources) != 1:
            errors["insight"] = "Cada enllaç ha d'apuntar exactament a una evidència."
        athlete_id = self.insight.athlete_profile_id if self.insight_id else None
        if (
            self.insight_id
            and self.observation_id
            and self.observation.athlete_id != self.insight.athlete_profile.person_id
        ):
            errors["observation"] = "L'observació correspon a un altre gimnasta."
        if self.measurement_id and self.measurement.athlete_profile_id != athlete_id:
            errors["measurement"] = "La mesura correspon a un altre gimnasta."
        if self.condition_id and self.condition.athlete_profile_id != athlete_id:
            errors["condition"] = "La condició correspon a un altre gimnasta."
        if (
            self.training_item_result_id
            and self.training_item_result.athlete_profile_id != athlete_id
        ):
            errors["training_item_result"] = "El resultat correspon a un altre gimnasta."
        if self.insight_id and self.insight.status != AthleteInsight.Status.PROPOSED:
            errors["insight"] = "Només es pot afegir evidència a una interpretació proposada."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args, **kwargs):
        if self.insight.status != AthleteInsight.Status.PROPOSED:
            raise ValidationError(
                "No es pot retirar evidència d'una interpretació ja revisada."
            )
        return super().delete(*args, **kwargs)
