from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from core.models import Person
from iatrain_motion.models import (
    EditorialStatus,
    JointAngleDefinition,
    MotionConcept,
    governed_content_changed,
    normalize_code,
    normalize_label,
)


class EvidenceReference(models.Model):
    class SourceType(models.TextChoices):
        ANATOMY_ONTOLOGY = "anatomy_ontology", "Ontologia anatòmica"
        TEXTBOOK = "textbook", "Manual o llibre de referència"
        PEER_REVIEWED = "peer_reviewed", "Publicació revisada per parells"
        PROFESSIONAL_CONSENSUS = "professional_consensus", "Consens professional"
        COMPUTATIONAL_MODEL = "computational_model", "Model computacional"
        OTHER = "other", "Altres"

    class IdentifierType(models.TextChoices):
        DOI = "doi", "DOI"
        ISBN = "isbn", "ISBN"
        URL = "url", "URL"
        ONTOLOGY = "ontology", "Identificador ontològic"
        OTHER = "other", "Altres"

    code = models.CharField(max_length=120, unique=True)
    title = models.CharField(max_length=300)
    source_type = models.CharField(max_length=40, choices=SourceType.choices)
    identifier_type = models.CharField(max_length=30, choices=IdentifierType.choices)
    identifier = models.CharField(max_length=300)
    url = models.URLField(blank=True, default="")
    citation = models.TextField(blank=True, default="")
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_biomechanical_evidence_references",
    )
    provenance = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("identifier_type", "identifier"),
                name="biomech_evidence_uniq_identifier",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        self.title = normalize_label(self.title)
        self.identifier = normalize_label(self.identifier)
        errors = {}
        if not self.code:
            errors["code"] = "La referència necessita un codi estable."
        if not self.title:
            errors["title"] = "La referència necessita un títol."
        if not self.identifier:
            errors["identifier"] = "La referència necessita un identificador."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if self.pk:
            governed_fields = (
                "code", "title", "source_type", "identifier_type", "identifier",
                "url", "citation", "provenance",
            )
            previous = type(self).objects.filter(pk=self.pk).values(*governed_fields).first()
            changed = previous and any(
                previous[field_name] != getattr(self, field_name)
                for field_name in governed_fields
            )
            if changed and (
                self.muscle_action_functions.filter(
                    editorial_status=EditorialStatus.VALIDATED
                ).exists()
                or self.muscle_stabilization_functions.filter(
                    editorial_status=EditorialStatus.VALIDATED
                ).exists()
            ):
                errors["citation"] = (
                    "Reobre les afirmacions validades abans de modificar-ne la font."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Les fonts no s'eliminen mentre poden sostenir afirmacions històriques.")

    def __str__(self):
        return self.title


class GovernedBiomechanicalModel(models.Model):
    code = models.CharField(max_length=140, unique=True)
    editorial_status = models.CharField(
        max_length=20,
        choices=EditorialStatus.choices,
        default=EditorialStatus.DRAFT,
    )
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_authored",
    )
    last_validated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_validated",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
    provenance = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def governed_fields(self):
        return ("code", "provenance")

    def governed_errors(self):
        self.code = normalize_code(self.code)
        errors = {}
        if not self.code:
            errors["code"] = "El registre necessita un codi estable."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if self._state.adding and self.editorial_status != EditorialStatus.DRAFT:
            errors["editorial_status"] = "Un registre nou sempre ha d'entrar com a esborrany."
        if governed_content_changed(self, self.governed_fields()):
            errors["editorial_status"] = "Reobre el registre abans de modificar contingut validat."
        return errors

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El coneixement biomecànic no s'elimina; es retira editorialment.")


class BiomechanicalContext(GovernedBiomechanicalModel):
    class KineticChain(models.TextChoices):
        UNSPECIFIED = "unspecified", "No especificada"
        OPEN = "open", "Cadena oberta"
        CLOSED = "closed", "Cadena tancada"
        EITHER = "either", "Aplicable a ambdues"

    name = models.CharField(max_length=220)
    description = models.TextField(blank=True, default="")
    kinetic_chain = models.CharField(
        max_length=20,
        choices=KineticChain.choices,
        default=KineticChain.UNSPECIFIED,
    )
    loading_conditions = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(Lower("name"), name="biomech_context_uniq_name"),
        ]

    def governed_fields(self):
        return (
            "code", "name", "description", "kinetic_chain", "loading_conditions", "provenance",
        )

    def clean(self):
        super().clean()
        self.name = normalize_label(self.name)
        errors = self.governed_errors()
        if not self.name:
            errors["name"] = "El context necessita un nom."
        if not isinstance(self.loading_conditions, dict):
            errors["loading_conditions"] = "Les condicions de càrrega han de ser un objecte JSON."
        if self.editorial_status == EditorialStatus.VALIDATED and not self.description.strip():
            errors["description"] = "Un context validat necessita una descripció professional."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.name


class ContextAngleConstraint(models.Model):
    class Effect(models.TextChoices):
        APPLICABLE = "applicable", "Aplicable"
        ENHANCED = "enhanced", "Contribució augmentada"
        REDUCED = "reduced", "Contribució reduïda"
        REVERSED = "reversed", "Efecte mecànic invertit"

    context = models.ForeignKey(
        BiomechanicalContext,
        on_delete=models.CASCADE,
        related_name="angle_constraints",
    )
    code = models.CharField(max_length=140)
    angle_definition = models.ForeignKey(
        JointAngleDefinition,
        on_delete=models.PROTECT,
        related_name="biomechanical_context_constraints",
    )
    minimum_radians = models.FloatField(null=True, blank=True)
    maximum_radians = models.FloatField(null=True, blank=True)
    effect = models.CharField(max_length=20, choices=Effect.choices, default=Effect.APPLICABLE)
    notes = models.TextField(blank=True, default="")
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_biomechanical_angle_constraints",
    )
    provenance = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("context_id", "code", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("context", "code"),
                name="biomech_context_angle_uniq_code",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        errors = {}
        if self.context_id and self.context.editorial_status == EditorialStatus.VALIDATED:
            errors["context"] = "Reobre el context abans de modificar-ne les restriccions angulars."
        if self.minimum_radians is None and self.maximum_radians is None:
            errors["minimum_radians"] = "Cal indicar almenys un límit angular."
        if (
            self.minimum_radians is not None
            and self.maximum_radians is not None
            and self.minimum_radians > self.maximum_radians
        ):
            errors["maximum_radians"] = "El màxim ha de ser igual o superior al mínim."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.context.editorial_status == EditorialStatus.VALIDATED:
            raise ValidationError("Reobre el context abans d'eliminar-ne una restricció.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.context}: {self.code}"


class MuscleActionFunction(GovernedBiomechanicalModel):
    class ContributionClass(models.TextChoices):
        MAJOR = "major", "Contribució mecànica principal"
        SUPPORTING = "supporting", "Contribució de suport"
        VARIABLE = "variable", "Contribució dependent del context"
        UNSPECIFIED = "unspecified", "No jerarquitzada"

    muscle = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="biomechanical_action_functions",
    )
    action = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="muscular_contributors",
    )
    context = models.ForeignKey(
        BiomechanicalContext,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="muscle_action_functions",
    )
    contribution_class = models.CharField(
        max_length=20,
        choices=ContributionClass.choices,
        default=ContributionClass.UNSPECIFIED,
    )
    statement = models.TextField()
    conditions = models.JSONField(blank=True, default=dict)
    limitations = models.TextField(blank=True, default="")
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="superseded_by",
    )
    evidence = models.ManyToManyField(
        EvidenceReference,
        through="MuscleActionFunctionEvidence",
        related_name="muscle_action_functions",
    )

    class Meta:
        ordering = ("muscle_id", "action_id", "context_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("muscle", "action"),
                condition=Q(context__isnull=True),
                name="biomech_action_function_uniq_general",
            ),
            models.UniqueConstraint(
                fields=("muscle", "action", "context"),
                condition=Q(context__isnull=False),
                name="biomech_action_function_uniq_context",
            ),
            models.CheckConstraint(
                check=~Q(supersedes=F("id")),
                name="biomech_action_function_no_self_supersede",
            ),
        ]
        indexes = [
            models.Index(
                fields=("muscle", "editorial_status"),
                name="biomech_action_muscle_idx",
            ),
            models.Index(
                fields=("action", "editorial_status"),
                name="biomech_action_target_idx",
            ),
        ]

    def governed_fields(self):
        return (
            "code", "muscle_id", "action_id", "context_id", "contribution_class",
            "statement", "conditions", "limitations", "supersedes_id", "provenance",
        )

    def clean(self):
        super().clean()
        errors = self.governed_errors()
        if self.muscle_id and self.muscle.kind != MotionConcept.Kind.MUSCLE:
            errors["muscle"] = "La funció ha de referenciar un concepte de tipus muscle."
        if self.action_id and self.action.kind != MotionConcept.Kind.JOINT_ACTION:
            errors["action"] = "La funció ha de referenciar una acció articular."
        if not isinstance(self.conditions, dict):
            errors["conditions"] = "Les condicions han de ser un objecte JSON."
        if not self.statement.strip():
            errors["statement"] = "Cal descriure l'afirmació biomecànica."
        if self.supersedes_id:
            if self.pk and self.supersedes_id == self.pk:
                errors["supersedes"] = "Una afirmació no es pot substituir a si mateixa."
            elif (
                self.supersedes.muscle_id != self.muscle_id
                or self.supersedes.action_id != self.action_id
            ):
                errors["supersedes"] = "Una revisió ha de conservar el mateix múscul i acció."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.muscle} → {self.action}"


class MuscleStabilizationFunction(GovernedBiomechanicalModel):
    class StabilizationType(models.TextChoices):
        JOINT_CENTERING = "joint_centering", "Centratge articular"
        SEGMENT_CONTROL = "segment_control", "Control segmentari"
        CO_CONTRACTION = "co_contraction", "Cocontracció"
        FORCE_TRANSFER = "force_transfer", "Transferència de força"
        POSTURAL = "postural", "Control postural"

    muscle = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="biomechanical_stabilization_functions",
    )
    target_joint = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="muscular_joint_stabilizers",
    )
    target_segment = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="muscular_segment_stabilizers",
    )
    context = models.ForeignKey(
        BiomechanicalContext,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="muscle_stabilization_functions",
    )
    stabilization_type = models.CharField(max_length=30, choices=StabilizationType.choices)
    statement = models.TextField()
    conditions = models.JSONField(blank=True, default=dict)
    limitations = models.TextField(blank=True, default="")
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="superseded_by",
    )
    evidence = models.ManyToManyField(
        EvidenceReference,
        through="MuscleStabilizationEvidence",
        related_name="muscle_stabilization_functions",
    )

    class Meta:
        ordering = ("muscle_id", "stabilization_type", "id")
        constraints = [
            models.CheckConstraint(
                check=(Q(target_joint__isnull=False, target_segment__isnull=True)
                       | Q(target_joint__isnull=True, target_segment__isnull=False)),
                name="biomech_stabilization_exactly_one_target",
            ),
            models.CheckConstraint(
                check=~Q(supersedes=F("id")),
                name="biomech_stabilization_no_self_supersede",
            ),
            models.UniqueConstraint(
                fields=("muscle", "target_joint", "stabilization_type"),
                condition=Q(context__isnull=True, target_joint__isnull=False),
                name="biomech_stabilization_uniq_general_joint",
            ),
            models.UniqueConstraint(
                fields=("muscle", "target_segment", "stabilization_type"),
                condition=Q(context__isnull=True, target_segment__isnull=False),
                name="biomech_stabilization_uniq_general_segment",
            ),
        ]

    def governed_fields(self):
        return (
            "code", "muscle_id", "target_joint_id", "target_segment_id", "context_id",
            "stabilization_type", "statement", "conditions", "limitations",
            "supersedes_id", "provenance",
        )

    def clean(self):
        super().clean()
        errors = self.governed_errors()
        if self.muscle_id and self.muscle.kind != MotionConcept.Kind.MUSCLE:
            errors["muscle"] = "La funció ha de referenciar un concepte de tipus muscle."
        if bool(self.target_joint_id) == bool(self.target_segment_id):
            errors["target_joint"] = "Cal indicar exactament una articulació o un segment."
        if self.target_joint_id and self.target_joint.kind != MotionConcept.Kind.JOINT:
            errors["target_joint"] = "L'objectiu articular ha de ser de tipus joint."
        if self.target_segment_id and self.target_segment.kind != MotionConcept.Kind.SEGMENT:
            errors["target_segment"] = "L'objectiu segmentari ha de ser de tipus segment."
        if not isinstance(self.conditions, dict):
            errors["conditions"] = "Les condicions han de ser un objecte JSON."
        if not self.statement.strip():
            errors["statement"] = "Cal descriure la funció estabilitzadora."
        if self.supersedes_id:
            if self.pk and self.supersedes_id == self.pk:
                errors["supersedes"] = "Una afirmació no es pot substituir a si mateixa."
            else:
                previous_target = self.supersedes.target_joint_id or self.supersedes.target_segment_id
                current_target = self.target_joint_id or self.target_segment_id
                if (
                    self.supersedes.muscle_id != self.muscle_id
                    or previous_target != current_target
                    or self.supersedes.stabilization_type != self.stabilization_type
                ):
                    errors["supersedes"] = (
                        "Una revisió ha de conservar múscul, objectiu i tipus d'estabilització."
                    )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        target = self.target_joint or self.target_segment
        return f"{self.muscle} → {target} ({self.get_stabilization_type_display()})"


class EvidenceLink(models.Model):
    class Relationship(models.TextChoices):
        SUPPORTS = "supports", "Sosté"
        QUALIFIES = "qualifies", "Matisa o limita"
        CONTRADICTS = "contradicts", "Contradiu"

    evidence = models.ForeignKey(EvidenceReference, on_delete=models.PROTECT)
    relationship = models.CharField(
        max_length=20,
        choices=Relationship.choices,
        default=Relationship.SUPPORTS,
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        abstract = True

    def _assert_parent_is_draft(self, parent):
        if parent.editorial_status != EditorialStatus.DRAFT:
            raise ValidationError("Reobre l'afirmació abans de modificar-ne l'evidència.")


class MuscleActionFunctionEvidence(EvidenceLink):
    function = models.ForeignKey(
        MuscleActionFunction,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("function", "evidence"),
                name="biomech_action_evidence_uniq",
            ),
        ]

    def save(self, *args, **kwargs):
        self._assert_parent_is_draft(self.function)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._assert_parent_is_draft(self.function)
        return super().delete(*args, **kwargs)


class MuscleStabilizationEvidence(EvidenceLink):
    function = models.ForeignKey(
        MuscleStabilizationFunction,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("function", "evidence"),
                name="biomech_stabilization_evidence_uniq",
            ),
        ]

    def save(self, *args, **kwargs):
        self._assert_parent_is_draft(self.function)
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._assert_parent_is_draft(self.function)
        return super().delete(*args, **kwargs)
