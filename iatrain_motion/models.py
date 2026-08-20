import re
import unicodedata

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from core.models import Person


def normalize_label(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split())


def normalize_code(value):
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"[^a-z0-9_]+", "_", re.sub(r"[\s-]+", "_", normalized)).strip("_")


def governed_content_changed(instance, field_names):
    if not instance.pk or instance.editorial_status != "validated":
        return False
    previous = type(instance).objects.filter(pk=instance.pk).values(
        "editorial_status", *field_names
    ).first()
    if not previous or previous["editorial_status"] != "validated":
        return False
    return any(previous[field] != getattr(instance, field) for field in field_names)


class EditorialStatus(models.TextChoices):
    DRAFT = "draft", "Esborrany"
    VALIDATED = "validated", "Validat"
    RETIRED = "retired", "Retirat"


class MotionConcept(models.Model):
    """A reusable node in the professional anatomical-kinematic subgraph."""

    class Kind(models.TextChoices):
        SEGMENT = "segment", "Segment corporal funcional"
        JOINT = "joint", "Articulació o complex articular"
        JOINT_ACTION = "joint_action", "Acció articular"
        PLANE = "plane", "Pla anatòmic"
        AXIS = "axis", "Eix anatòmic"
        BODY_CONFIGURATION = "body_configuration", "Configuració corporal"
        KINEMATIC_EVENT = "kinematic_event", "Esdeveniment cinemàtic"
        MUSCLE = "muscle", "Múscul esquelètic funcional"
        MUSCLE_GROUP = "muscle_group", "Grup muscular funcional"

    class Laterality(models.TextChoices):
        NOT_APPLICABLE = "not_applicable", "No aplicable"
        UNPAIRED = "unpaired", "Estructura no parella"
        MIDLINE = "midline", "Estructura medial"
        PAIRED = "paired", "Estructura parella"

    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Identificador semàntic estable, independent de l'idioma i del nom visible.",
    )
    name = models.CharField(max_length=220)
    definition = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=40, choices=Kind.choices)
    laterality = models.CharField(
        max_length=20,
        choices=Laterality.choices,
        default=Laterality.NOT_APPLICABLE,
        help_text="Classifica l'estructura; els costats concrets es modelaran en l'esquelet o l'ús.",
    )
    editorial_status = models.CharField(
        max_length=20,
        choices=EditorialStatus.choices,
        default=EditorialStatus.DRAFT,
    )
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_motion_concepts",
    )
    last_validated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_motion_concepts",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
    provenance = models.JSONField(
        blank=True,
        default=dict,
        help_text="Fonts, correspondències externes i notes de procedència estructurades.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("kind", "name", "id")
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "kind",
                name="motion_concept_uniq_name_kind",
            ),
        ]
        indexes = [
            models.Index(
                fields=("kind", "editorial_status"),
                name="motion_concept_scope_idx",
            ),
            models.Index(
                fields=("authored_by", "created_at"),
                name="motion_concept_author_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        self.name = normalize_label(self.name)
        errors = {}
        if not self.code:
            errors["code"] = "El concepte necessita un codi estable."
        if not self.name:
            errors["name"] = "El concepte necessita un nom."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if self._state.adding and self.editorial_status != EditorialStatus.DRAFT:
            errors["editorial_status"] = "Un concepte nou sempre ha d'entrar com a esborrany."

        anatomical_kinds = {
            self.Kind.SEGMENT,
            self.Kind.JOINT,
            self.Kind.MUSCLE,
            self.Kind.MUSCLE_GROUP,
        }
        if self.kind in anatomical_kinds and self.laterality == self.Laterality.NOT_APPLICABLE:
            errors["laterality"] = "Una estructura anatòmica ha de declarar la seva lateralitat."
        if self.kind not in anatomical_kinds and self.laterality != self.Laterality.NOT_APPLICABLE:
            errors["laterality"] = "La lateralitat només classifica estructures anatòmiques."
        if self.editorial_status == EditorialStatus.VALIDATED and not self.definition.strip():
            errors["definition"] = "Un concepte validat necessita una definició professional."
        if governed_content_changed(
            self,
            ("code", "name", "definition", "kind", "laterality", "provenance"),
        ):
            errors["editorial_status"] = (
                "Reobre el concepte com a esborrany abans de modificar contingut validat."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Els conceptes anatòmics no s'eliminen; retira'ls mitjançant el servei editorial."
        )

    def __str__(self):
        return self.name


class MotionRelation(models.Model):
    """A typed edge whose domain and range are part of the anatomical contract."""

    class RelationType(models.TextChoices):
        PART_OF = "part_of", "Forma part de"
        PROXIMAL_SEGMENT = "proximal_segment", "Té com a segment proximal"
        DISTAL_SEGMENT = "distal_segment", "Té com a segment distal"
        ACTION_AT_JOINT = "action_at_joint", "Es produeix a l'articulació"
        PRIMARY_PLANE = "primary_plane", "Es produeix principalment al pla"
        PRIMARY_AXIS = "primary_axis", "Es produeix principalment al voltant de l'eix"
        OPPOSITE_OF = "opposite_of", "És oposada a"
        MEMBER_OF_MUSCLE_GROUP = "member_of_muscle_group", "Forma part del grup muscular"
        SPANS_JOINT = "spans_joint", "Travessa funcionalment l'articulació"

    source = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="outgoing_motion_relations",
    )
    target = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="incoming_motion_relations",
    )
    relation_type = models.CharField(max_length=40, choices=RelationType.choices)
    rationale = models.TextField(blank=True, default="")
    editorial_status = models.CharField(
        max_length=20,
        choices=EditorialStatus.choices,
        default=EditorialStatus.DRAFT,
    )
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_motion_relations",
    )
    last_validated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_motion_relations",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
    provenance = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("source_id", "relation_type", "target_id")
        constraints = [
            models.CheckConstraint(
                check=~Q(source=F("target")),
                name="motion_relation_distinct_nodes",
            ),
            models.UniqueConstraint(
                fields=("source", "target", "relation_type"),
                name="motion_relation_uniq_edge",
            ),
            models.UniqueConstraint(
                fields=("source", "relation_type"),
                condition=Q(
                    relation_type__in=(
                        "proximal_segment",
                        "distal_segment",
                        "action_at_joint",
                        "primary_plane",
                        "primary_axis",
                    )
                ),
                name="motion_relation_uniq_functional",
            ),
        ]
        indexes = [
            models.Index(
                fields=("source", "relation_type", "editorial_status"),
                name="motion_rel_source_idx",
            ),
            models.Index(
                fields=("target", "relation_type", "editorial_status"),
                name="motion_rel_target_idx",
            ),
        ]

    @classmethod
    def expected_endpoint_kinds(cls):
        kind = MotionConcept.Kind
        return {
            cls.RelationType.PART_OF: (kind.SEGMENT, kind.SEGMENT),
            cls.RelationType.PROXIMAL_SEGMENT: (kind.JOINT, kind.SEGMENT),
            cls.RelationType.DISTAL_SEGMENT: (kind.JOINT, kind.SEGMENT),
            cls.RelationType.ACTION_AT_JOINT: (kind.JOINT_ACTION, kind.JOINT),
            cls.RelationType.PRIMARY_PLANE: (kind.JOINT_ACTION, kind.PLANE),
            cls.RelationType.PRIMARY_AXIS: (kind.JOINT_ACTION, kind.AXIS),
            cls.RelationType.OPPOSITE_OF: (kind.JOINT_ACTION, kind.JOINT_ACTION),
            cls.RelationType.MEMBER_OF_MUSCLE_GROUP: (kind.MUSCLE, kind.MUSCLE_GROUP),
            cls.RelationType.SPANS_JOINT: (kind.MUSCLE, kind.JOINT),
        }

    def clean(self):
        super().clean()
        errors = {}
        if self.source_id and self.source_id == self.target_id:
            errors["target"] = "Una relació anatòmica no pot apuntar al mateix node."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if self._state.adding and self.editorial_status != EditorialStatus.DRAFT:
            errors["editorial_status"] = "Una relació nova sempre ha d'entrar com a esborrany."

        endpoints = {}
        if self.source_id and self.target_id:
            endpoints = {
                row["id"]: row
                for row in MotionConcept.objects.filter(
                    pk__in=(self.source_id, self.target_id)
                ).values("id", "kind", "editorial_status")
            }
        if len(endpoints) == len({self.source_id, self.target_id}) == 2:
            expected = self.expected_endpoint_kinds().get(self.relation_type)
            actual = (endpoints[self.source_id]["kind"], endpoints[self.target_id]["kind"])
            if expected and actual != expected:
                errors["relation_type"] = (
                    f"{self.relation_type} requereix origen {expected[0]} i destí {expected[1]}."
                )
            if self.editorial_status == EditorialStatus.VALIDATED and any(
                endpoints[node_id]["editorial_status"] != EditorialStatus.VALIDATED
                for node_id in (self.source_id, self.target_id)
            ):
                errors["editorial_status"] = (
                    "Una relació validada només pot connectar conceptes validats."
                )
        if (
            self.relation_type == self.RelationType.OPPOSITE_OF
            and self.source_id
            and self.target_id
            and self.source_id > self.target_id
        ):
            errors["source"] = (
                "Les relacions simètriques opposite_of s'emmagatzemen amb l'identificador menor com a origen."
            )
        if governed_content_changed(
            self,
            ("source_id", "target_id", "relation_type", "rationale", "provenance"),
        ):
            errors["editorial_status"] = (
                "Reobre la relació com a esborrany abans de modificar contingut validat."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Les relacions anatòmiques no s'eliminen; retira-les mitjançant el servei editorial."
        )

    def __str__(self):
        return f"{self.source} —{self.get_relation_type_display()}→ {self.target}"


class SkeletonSide(models.TextChoices):
    NONE = "none", "Sense lateralitat"
    MIDLINE = "midline", "Medial"
    LEFT = "left", "Esquerra"
    RIGHT = "right", "Dreta"


def _schema_is_locked(instance):
    if not instance.schema_id:
        return False
    return instance.schema.editorial_status == EditorialStatus.VALIDATED


def _validate_semantic_laterality(*, concept, side, field_name="side"):
    if concept.laterality == MotionConcept.Laterality.PAIRED and side not in {
        SkeletonSide.LEFT,
        SkeletonSide.RIGHT,
    }:
        return {field_name: "Un concepte parell necessita una instància esquerra o dreta."}
    if concept.laterality == MotionConcept.Laterality.MIDLINE and side != SkeletonSide.MIDLINE:
        return {field_name: "Un concepte medial necessita una instància medial."}
    if concept.laterality == MotionConcept.Laterality.UNPAIRED and side != SkeletonSide.NONE:
        return {field_name: "Un concepte no parell no pot tenir costat."}
    return {}


class SkeletonSchema(models.Model):
    """Versioned measurement contract that instantiates the semantic motion graph."""

    class Dimension(models.IntegerChoices):
        TWO_D = 2, "2D"
        THREE_D = 3, "3D"

    code = models.CharField(max_length=100)
    version = models.CharField(max_length=40)
    name = models.CharField(max_length=220)
    description = models.TextField(blank=True, default="")
    spatial_dimensions = models.PositiveSmallIntegerField(
        choices=Dimension.choices,
        default=Dimension.THREE_D,
    )
    length_unit = models.CharField(max_length=20, default="metre")
    angle_unit = models.CharField(max_length=20, default="radian")
    coordinate_convention = models.JSONField(blank=True, default=dict)
    neutral_pose = models.JSONField(blank=True, default=dict)
    editorial_status = models.CharField(
        max_length=20,
        choices=EditorialStatus.choices,
        default=EditorialStatus.DRAFT,
    )
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_skeleton_schemas",
    )
    last_validated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_skeleton_schemas",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
    provenance = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("code", "version", "id")
        constraints = [
            models.UniqueConstraint(
                Lower("code"),
                "version",
                name="skeleton_schema_uniq_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=("editorial_status", "code"),
                name="skeleton_schema_scope_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        self.name = normalize_label(self.name)
        self.version = normalize_label(self.version)
        self.length_unit = normalize_code(self.length_unit)
        self.angle_unit = normalize_code(self.angle_unit)
        errors = {}
        if not self.code:
            errors["code"] = "L'esquema necessita un codi estable."
        if not self.name:
            errors["name"] = "L'esquema necessita un nom."
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9a-z._-]+)?", self.version):
            errors["version"] = "La versió ha de seguir una forma semàntica com 1.0.0 o 1.0.0-draft."
        if self.length_unit != "metre":
            errors["length_unit"] = "La unitat canònica interna ha de ser el metre."
        if self.angle_unit != "radian":
            errors["angle_unit"] = "La unitat canònica interna ha de ser el radiant."
        if not isinstance(self.coordinate_convention, dict):
            errors["coordinate_convention"] = "La convenció de coordenades ha de ser un objecte JSON."
        elif self.editorial_status == EditorialStatus.VALIDATED:
            required = {"handedness", "axes", "segment_frames"}
            missing = sorted(required - set(self.coordinate_convention))
            if missing:
                errors["coordinate_convention"] = f"Falten convencions obligatòries: {', '.join(missing)}."
        if not isinstance(self.neutral_pose, dict):
            errors["neutral_pose"] = "La posició neutra ha de ser un objecte JSON."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if self._state.adding and self.editorial_status != EditorialStatus.DRAFT:
            errors["editorial_status"] = "Un esquema nou sempre ha d'entrar com a esborrany."
        if self.editorial_status == EditorialStatus.VALIDATED and not self.description.strip():
            errors["description"] = "Un esquema validat necessita una descripció professional."
        if governed_content_changed(
            self,
            (
                "code",
                "version",
                "name",
                "description",
                "spatial_dimensions",
                "length_unit",
                "angle_unit",
                "coordinate_convention",
                "neutral_pose",
                "provenance",
            ),
        ):
            errors["editorial_status"] = "Reobre l'esquema abans de modificar-ne el contracte."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Els esquemes canònics no s'eliminen; es retiren editorialment.")

    def __str__(self):
        return f"{self.name} · {self.version}"


class SkeletonDefinition(models.Model):
    """Authored child definition governed as part of one SkeletonSchema aggregate."""

    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_authored",
    )
    provenance = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def _base_errors(self):
        errors = {}
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if _schema_is_locked(self):
            previous = type(self).objects.filter(pk=self.pk).exists() if self.pk else False
            if not previous:
                errors["schema"] = "Reobre l'esquema abans d'afegir-hi definicions."
            else:
                errors["schema"] = "Reobre l'esquema abans de modificar-ne definicions."
        return errors

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if _schema_is_locked(self):
            raise ValidationError("Reobre l'esquema abans d'eliminar-ne una definició.")
        return super().delete(*args, **kwargs)


class CanonicalLandmark(SkeletonDefinition):
    class LandmarkType(models.TextChoices):
        ANATOMICAL = "anatomical", "Punt anatòmic"
        JOINT_CENTER = "joint_center", "Centre articular"
        VIRTUAL = "virtual", "Punt virtual derivat"
        TERMINAL = "terminal", "Punt terminal de segment"

    class MeasurementSource(models.TextChoices):
        OBSERVED = "observed", "Observable o mapable des d'un tracker"
        DERIVED = "derived", "Derivat d'altres punts"
        ESTIMATED = "estimated", "Centre o punt estimat"

    schema = models.ForeignKey(
        SkeletonSchema,
        on_delete=models.CASCADE,
        related_name="landmarks",
    )
    code = models.CharField(max_length=120)
    name = models.CharField(max_length=220)
    definition = models.TextField(blank=True, default="")
    landmark_type = models.CharField(max_length=30, choices=LandmarkType.choices)
    measurement_source = models.CharField(max_length=20, choices=MeasurementSource.choices)
    side = models.CharField(max_length=20, choices=SkeletonSide.choices, default=SkeletonSide.NONE)
    derivation = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ("schema_id", "side", "code", "id")
        constraints = [
            models.UniqueConstraint(fields=("schema", "code"), name="skeleton_landmark_uniq_code"),
        ]
        indexes = [
            models.Index(fields=("schema", "side"), name="skeleton_landmark_side_idx"),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        self.name = normalize_label(self.name)
        errors = self._base_errors()
        if not self.code:
            errors["code"] = "El punt necessita un codi estable."
        if not self.name:
            errors["name"] = "El punt necessita un nom."
        if not isinstance(self.derivation, dict):
            errors["derivation"] = "La derivació ha de ser un objecte JSON."
        elif self.measurement_source == self.MeasurementSource.DERIVED:
            if not self.derivation.get("method") or not self.derivation.get("inputs"):
                errors["derivation"] = "Un punt derivat necessita method i inputs."
        if self.measurement_source != self.MeasurementSource.DERIVED and self.derivation:
            errors["derivation"] = "Només els punts derivats poden declarar una fórmula de derivació."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} ({self.schema.version})"


class CanonicalSegment(SkeletonDefinition):
    class OrientationCapability(models.TextChoices):
        LONG_AXIS_ONLY = "long_axis_only", "Només eix longitudinal"
        FULL_3D = "full_3d", "Orientació tridimensional"

    class PrimaryAxis(models.TextChoices):
        LONGITUDINAL = "longitudinal", "Longitudinal"
        MEDIOLATERAL = "mediolateral", "Mediolateral"

    schema = models.ForeignKey(
        SkeletonSchema,
        on_delete=models.CASCADE,
        related_name="segments",
    )
    code = models.CharField(max_length=120)
    concept = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="canonical_segment_instances",
    )
    side = models.CharField(max_length=20, choices=SkeletonSide.choices, default=SkeletonSide.NONE)
    axis_start_landmark = models.ForeignKey(
        CanonicalLandmark,
        on_delete=models.PROTECT,
        related_name="segment_axes_starting_here",
    )
    axis_end_landmark = models.ForeignKey(
        CanonicalLandmark,
        on_delete=models.PROTECT,
        related_name="segment_axes_ending_here",
    )
    plane_landmark = models.ForeignKey(
        CanonicalLandmark,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="segments_defining_plane_here",
    )
    orientation_capability = models.CharField(
        max_length=30,
        choices=OrientationCapability.choices,
        default=OrientationCapability.LONG_AXIS_ONLY,
    )
    primary_axis = models.CharField(
        max_length=20,
        choices=PrimaryAxis.choices,
        default=PrimaryAxis.LONGITUDINAL,
    )
    frame_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("schema_id", "side", "code", "id")
        constraints = [
            models.UniqueConstraint(fields=("schema", "code"), name="skeleton_segment_uniq_code"),
            models.UniqueConstraint(
                fields=("schema", "concept", "side"),
                name="skeleton_segment_uniq_semantic",
            ),
            models.CheckConstraint(
                check=~Q(axis_start_landmark=F("axis_end_landmark")),
                name="skeleton_segment_distinct_ends",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        errors = self._base_errors()
        if self.concept_id and self.concept.kind != MotionConcept.Kind.SEGMENT:
            errors["concept"] = "Una instància de segment ha de referenciar un concepte segment."
        if self.concept_id:
            errors.update(_validate_semantic_laterality(concept=self.concept, side=self.side))
        landmarks = [self.axis_start_landmark, self.axis_end_landmark, self.plane_landmark]
        for landmark in filter(None, landmarks):
            if self.schema_id and landmark.schema_id != self.schema_id:
                errors["schema"] = "Tots els punts del segment han de pertànyer al mateix esquema."
        if self.axis_start_landmark_id and self.axis_start_landmark_id == self.axis_end_landmark_id:
            errors["axis_end_landmark"] = "Els punts que defineixen l'eix han de ser diferents."
        if self.orientation_capability == self.OrientationCapability.FULL_3D:
            if not self.plane_landmark_id:
                errors["plane_landmark"] = "Una orientació 3D necessita un tercer punt que defineixi el pla."
            elif self.plane_landmark_id in {self.axis_start_landmark_id, self.axis_end_landmark_id}:
                errors["plane_landmark"] = "El tercer punt ha de ser diferent dels extrems."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.code} · {self.schema.version}"


class CanonicalJoint(SkeletonDefinition):
    schema = models.ForeignKey(
        SkeletonSchema,
        on_delete=models.CASCADE,
        related_name="joints",
    )
    code = models.CharField(max_length=120)
    concept = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="canonical_joint_instances",
    )
    side = models.CharField(max_length=20, choices=SkeletonSide.choices, default=SkeletonSide.NONE)
    center_landmark = models.OneToOneField(
        CanonicalLandmark,
        on_delete=models.PROTECT,
        related_name="joint_definition",
    )
    proximal_segment = models.ForeignKey(
        CanonicalSegment,
        on_delete=models.PROTECT,
        related_name="distal_joints",
    )
    distal_segment = models.ForeignKey(
        CanonicalSegment,
        on_delete=models.PROTECT,
        related_name="proximal_joints",
    )

    class Meta:
        ordering = ("schema_id", "side", "code", "id")
        constraints = [
            models.UniqueConstraint(fields=("schema", "code"), name="skeleton_joint_uniq_code"),
            models.UniqueConstraint(
                fields=("schema", "concept", "side"),
                name="skeleton_joint_uniq_semantic",
            ),
            models.CheckConstraint(
                check=~Q(proximal_segment=F("distal_segment")),
                name="skeleton_joint_distinct_segments",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        errors = self._base_errors()
        if self.concept_id and self.concept.kind != MotionConcept.Kind.JOINT:
            errors["concept"] = "Una instància articular ha de referenciar un concepte articulació."
        if self.concept_id:
            errors.update(_validate_semantic_laterality(concept=self.concept, side=self.side))
        definitions = (self.center_landmark, self.proximal_segment, self.distal_segment)
        for definition in filter(None, definitions):
            if self.schema_id and definition.schema_id != self.schema_id:
                errors["schema"] = "El centre i els segments de l'articulació han de ser del mateix esquema."
        if self.proximal_segment_id and self.proximal_segment_id == self.distal_segment_id:
            errors["distal_segment"] = "Els segments proximal i distal han de ser diferents."
        if self.center_landmark_id and self.center_landmark.side not in {self.side, SkeletonSide.MIDLINE}:
            errors["center_landmark"] = "El costat del centre articular no coincideix amb l'articulació."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.code} · {self.schema.version}"


class JointAngleDefinition(SkeletonDefinition):
    class Component(models.TextChoices):
        FLEXION_EXTENSION = "flexion_extension", "Flexió-extensió"
        ABDUCTION_ADDUCTION = "abduction_adduction", "Abducció-adducció"
        AXIAL_ROTATION = "axial_rotation", "Rotació axial"
        HORIZONTAL_ABDUCTION_ADDUCTION = (
            "horizontal_abduction_adduction",
            "Abducció-adducció horitzontal",
        )
        RADIAL_ULNAR_DEVIATION = "radial_ulnar_deviation", "Desviació radial-cubital"
        INVERSION_EVERSION = "inversion_eversion", "Inversió-eversió"

    class CalculationMethod(models.TextChoices):
        PROJECTED_PLANAR = "projected_planar", "Angle planar projectat"
        JOINT_COORDINATE_SYSTEM = "joint_coordinate_system", "Sistema de coordenades articular"

    schema = models.ForeignKey(
        SkeletonSchema,
        on_delete=models.CASCADE,
        related_name="angle_definitions",
    )
    code = models.CharField(max_length=140)
    joint = models.ForeignKey(
        CanonicalJoint,
        on_delete=models.PROTECT,
        related_name="angle_definitions",
    )
    component = models.CharField(max_length=40, choices=Component.choices)
    sequence_index = models.PositiveSmallIntegerField(default=1)
    positive_action = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="positive_joint_angle_definitions",
    )
    negative_action = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="negative_joint_angle_definitions",
    )
    plane = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="planar_joint_angle_definitions",
    )
    axis = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="axial_joint_angle_definitions",
    )
    calculation_method = models.CharField(max_length=40, choices=CalculationMethod.choices)
    sign_convention = models.TextField()

    class Meta:
        ordering = ("schema_id", "joint_id", "sequence_index", "id")
        constraints = [
            models.UniqueConstraint(fields=("schema", "code"), name="skeleton_angle_uniq_code"),
            models.UniqueConstraint(
                fields=("joint", "component"),
                name="skeleton_angle_uniq_component",
            ),
            models.CheckConstraint(
                check=~Q(positive_action=F("negative_action")),
                name="skeleton_angle_distinct_actions",
            ),
            models.CheckConstraint(
                check=Q(sequence_index__gte=1, sequence_index__lte=3),
                name="skeleton_angle_sequence_range",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        errors = self._base_errors()
        if self.joint_id and self.schema_id and self.joint.schema_id != self.schema_id:
            errors["joint"] = "L'angle i l'articulació han de pertànyer al mateix esquema."
        expected_kinds = {
            "positive_action": MotionConcept.Kind.JOINT_ACTION,
            "negative_action": MotionConcept.Kind.JOINT_ACTION,
            "plane": MotionConcept.Kind.PLANE,
            "axis": MotionConcept.Kind.AXIS,
        }
        for field_name, expected_kind in expected_kinds.items():
            concept = getattr(self, field_name, None)
            if concept and concept.kind != expected_kind:
                errors[field_name] = f"El concepte ha de ser de tipus {expected_kind}."
        if self.positive_action_id and self.positive_action_id == self.negative_action_id:
            errors["negative_action"] = "Les direccions positiva i negativa han de ser accions diferents."
        if not self.sign_convention.strip():
            errors["sign_convention"] = "Cal documentar explícitament el signe de l'angle."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.code} · {self.schema.version}"
