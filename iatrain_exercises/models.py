from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from core.models import Person
from iatrain_biomechanics.models import (
    MuscleActionFunction,
    MuscleStabilizationFunction,
)
from iatrain_motion.models import (
    EditorialStatus,
    MotionConcept,
    governed_content_changed,
    normalize_code,
    normalize_label,
)


class ExerciseCatalog(models.Model):
    """A catalog boundary. V1 deliberately supports personal catalogs only."""

    class Kind(models.TextChoices):
        PERSONAL = "personal", "Personal"

    owner = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="exercise_catalogs",
    )
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PERSONAL)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("owner_id", "name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "code"),
                name="exercise_catalog_uniq_owner_code",
            ),
            models.UniqueConstraint(
                Lower("name"),
                "owner",
                name="exercise_catalog_uniq_owner_name",
            ),
        ]
        indexes = [
            models.Index(
                fields=("owner", "is_active"),
                name="exercise_catalog_owner_idx",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        self.name = normalize_label(self.name)
        errors = {}
        if not self.code:
            errors["code"] = "El catàleg necessita un codi estable."
        if not self.name:
            errors["name"] = "El catàleg necessita un nom."
        if self.kind != self.Kind.PERSONAL:
            errors["kind"] = "La primera versió només admet catàlegs personals."
        if not self.owner_id or not self.owner.is_active:
            errors["owner"] = "El catàleg necessita una persona propietària activa."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Els catàlegs es desactiven; no s'eliminen.")

    def __str__(self):
        return f"{self.owner} · {self.name}"


class Equipment(models.Model):
    class Category(models.TextChoices):
        FREE_WEIGHT = "free_weight", "Pes lliure"
        ELASTIC = "elastic", "Resistència elàstica"
        SUPPORT = "support", "Suport o superfície"
        MACHINE = "machine", "Màquina"
        SUSPENSION = "suspension", "Suspensió"
        OTHER = "other", "Altres"

    catalog = models.ForeignKey(
        ExerciseCatalog,
        on_delete=models.PROTECT,
        related_name="equipment_definitions",
    )
    code = models.CharField(max_length=100)
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=30, choices=Category.choices)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("catalog_id", "category", "name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("catalog", "code"),
                name="exercise_equipment_uniq_code",
            ),
            models.UniqueConstraint(
                Lower("name"),
                "catalog",
                name="exercise_equipment_uniq_name",
            ),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        self.name = normalize_label(self.name)
        errors = {}
        if not self.code:
            errors["code"] = "El material necessita un codi estable."
        if not self.name:
            errors["name"] = "El material necessita un nom."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El material es desactiva; no s'elimina.")

    def __str__(self):
        return self.name


class Exercise(models.Model):
    """Stable, tenant-owned identity; descriptive claims live in revisions."""

    class Kind(models.TextChoices):
        FAMILY = "family", "Família d'exercicis"
        VARIANT = "variant", "Variant executable"

    catalog = models.ForeignKey(
        ExerciseCatalog,
        on_delete=models.PROTECT,
        related_name="exercises",
    )
    code = models.CharField(max_length=120)
    name = models.CharField(max_length=220)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="variants",
    )
    created_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="created_exercises",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("catalog_id", "name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("catalog", "code"),
                name="exercise_uniq_catalog_code",
            ),
            models.UniqueConstraint(
                Lower("name"),
                "catalog",
                name="exercise_uniq_catalog_name",
            ),
            models.CheckConstraint(
                check=(Q(kind="family", parent__isnull=True) | Q(kind="variant", parent__isnull=False)),
                name="exercise_kind_parent_consistent",
            ),
        ]
        indexes = [
            models.Index(fields=("catalog", "kind", "is_active"), name="exercise_catalog_kind_idx"),
        ]

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        self.name = normalize_label(self.name)
        errors = {}
        if not self.code:
            errors["code"] = "L'exercici necessita un codi estable dins del catàleg."
        if not self.name:
            errors["name"] = "L'exercici necessita un nom."
        if self.kind == self.Kind.FAMILY and self.parent_id:
            errors["parent"] = "Una família no pot dependre d'una altra família."
        if self.kind == self.Kind.VARIANT:
            if not self.parent_id:
                errors["parent"] = "Una variant necessita una família."
            elif self.parent.catalog_id != self.catalog_id:
                errors["parent"] = "La variant i la família han de pertànyer al mateix catàleg."
            elif self.parent.kind != self.Kind.FAMILY:
                errors["parent"] = "El pare d'una variant ha de ser una família."
        if self.created_by_id and self.created_by_id != self.catalog.owner_id:
            errors["created_by"] = "En un catàleg personal, el creador ha de ser el propietari."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Els exercicis es retiren del catàleg; no s'eliminen.")

    def __str__(self):
        return self.name


class ExerciseRevision(models.Model):
    class Modality(models.TextChoices):
        STRENGTH = "strength", "Força"
        POWER = "power", "Potència"
        MUSCULAR_ENDURANCE = "muscular_endurance", "Resistència muscular"
        MOTOR_CONTROL = "motor_control", "Control motor"
        MOBILITY = "mobility", "Mobilitat"
        WARM_UP = "warm_up", "Escalfament"

    class ExecutionType(models.TextChoices):
        DYNAMIC = "dynamic", "Dinàmic"
        ISOMETRIC = "isometric", "Isomètric"
        MIXED = "mixed", "Mixt"

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Inicial"
        INTERMEDIATE = "intermediate", "Intermedi"
        ADVANCED = "advanced", "Avançat"

    class Laterality(models.TextChoices):
        BILATERAL = "bilateral", "Bilateral"
        UNILATERAL = "unilateral", "Unilateral"
        ALTERNATING = "alternating", "Alternant"
        NOT_APPLICABLE = "not_applicable", "No aplicable"

    class KineticChain(models.TextChoices):
        OPEN = "open", "Cadena oberta"
        CLOSED = "closed", "Cadena tancada"
        MIXED = "mixed", "Mixta"
        UNSPECIFIED = "unspecified", "No especificada"

    class MovementPattern(models.TextChoices):
        SQUAT = "squat", "Esquat"
        HINGE = "hinge", "Frontissa de maluc"
        HORIZONTAL_PUSH = "horizontal_push", "Empenta horitzontal"
        VERTICAL_PUSH = "vertical_push", "Empenta vertical"
        HORIZONTAL_PULL = "horizontal_pull", "Tracció horitzontal"
        VERTICAL_PULL = "vertical_pull", "Tracció vertical"
        ANKLE_DOMINANT = "ankle_dominant", "Dominant de turmell"
        TRUNK_CONTROL = "trunk_control", "Control del tronc"
        LOCOMOTION = "locomotion", "Locomoció"
        OTHER = "other", "Altres"

    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="revisions")
    revision_number = models.PositiveSmallIntegerField(validators=(MinValueValidator(1),))
    editorial_status = models.CharField(
        max_length=20,
        choices=EditorialStatus.choices,
        default=EditorialStatus.DRAFT,
    )
    modality = models.CharField(max_length=30, choices=Modality.choices)
    execution_type = models.CharField(max_length=20, choices=ExecutionType.choices)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices)
    laterality = models.CharField(max_length=20, choices=Laterality.choices)
    kinetic_chain = models.CharField(max_length=20, choices=KineticChain.choices)
    movement_pattern = models.CharField(max_length=30, choices=MovementPattern.choices)
    description = models.TextField()
    setup = models.TextField()
    execution = models.TextField()
    coaching_cues = models.TextField()
    safety_notes = models.TextField(blank=True, default="")
    requires_equipment = models.BooleanField(default=False)
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_exercise_revisions",
    )
    last_validated_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_exercise_revisions",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
    supersedes = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="superseded_by",
    )
    provenance = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("exercise_id", "-revision_number", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("exercise", "revision_number"),
                name="exercise_revision_uniq_number",
            ),
            models.UniqueConstraint(
                fields=("exercise",),
                condition=Q(editorial_status="validated"),
                name="exercise_revision_one_validated",
            ),
            models.CheckConstraint(
                check=~Q(supersedes=F("id")),
                name="exercise_revision_no_self_supersede",
            ),
        ]
        indexes = [
            models.Index(
                fields=("exercise", "editorial_status"),
                name="exercise_revision_status_idx",
            ),
            models.Index(
                fields=("movement_pattern", "modality", "editorial_status"),
                name="exercise_revision_search_idx",
            ),
        ]

    def governed_fields(self):
        return (
            "exercise_id", "revision_number", "modality", "execution_type", "difficulty",
            "laterality", "kinetic_chain", "movement_pattern", "description", "setup",
            "execution", "coaching_cues", "safety_notes", "requires_equipment",
            "supersedes_id", "provenance",
        )

    def clean(self):
        super().clean()
        errors = {}
        if self._state.adding and self.editorial_status != EditorialStatus.DRAFT:
            errors["editorial_status"] = "Una revisió nova sempre entra com a esborrany."
        if self.exercise_id and self.authored_by_id != self.exercise.catalog.owner_id:
            errors["authored_by"] = "La revisió privada ha de ser propietat de l'autor del catàleg."
        for field_name in ("description", "setup", "execution", "coaching_cues"):
            if not str(getattr(self, field_name, "") or "").strip():
                errors[field_name] = "Aquest camp és necessari per descriure l'exercici."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if self.supersedes_id:
            if self.pk and self.supersedes_id == self.pk:
                errors["supersedes"] = "Una revisió no es pot substituir a si mateixa."
            elif self.supersedes.exercise_id != self.exercise_id:
                errors["supersedes"] = "Una revisió només pot substituir el mateix exercici."
            elif self.supersedes.revision_number >= self.revision_number:
                errors["revision_number"] = "La revisió nova ha de tenir un número superior."
        if governed_content_changed(self, self.governed_fields()):
            errors["editorial_status"] = "Crea una revisió nova abans de canviar contingut validat."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Les revisions es retiren editorialment; no s'eliminen.")

    def __str__(self):
        return f"{self.exercise} · v{self.revision_number}"


def _assert_revision_draft(revision):
    if revision.editorial_status != EditorialStatus.DRAFT:
        raise ValidationError("Només es pot modificar el detall d'una revisió en esborrany.")


class RevisionChildModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def parent_revision(self):
        raise NotImplementedError

    def save(self, *args, **kwargs):
        _assert_revision_draft(self.parent_revision())
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        _assert_revision_draft(self.parent_revision())
        return super().delete(*args, **kwargs)


class ExercisePhase(RevisionChildModel):
    class PhaseType(models.TextChoices):
        SETUP = "setup", "Preparació"
        ACTIVE = "active", "Activa"
        TRANSITION = "transition", "Transició"
        HOLD = "hold", "Manteniment"
        RECOVERY = "recovery", "Retorn o recuperació"

    class Intent(models.TextChoices):
        PRODUCE = "produce", "Produir el moviment"
        ASSIST = "assist", "Assistir el moviment"
        CONTROL = "control", "Controlar o frenar"
        HOLD = "hold", "Mantenir posició"
        REPOSITION = "reposition", "Reposicionar"

    revision = models.ForeignKey(
        ExerciseRevision,
        on_delete=models.CASCADE,
        related_name="phases",
    )
    sequence_index = models.PositiveSmallIntegerField(validators=(MinValueValidator(1),))
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=160)
    phase_type = models.CharField(max_length=20, choices=PhaseType.choices)
    intent = models.CharField(max_length=20, choices=Intent.choices)
    description = models.TextField()
    is_key_phase = models.BooleanField(default=False)
    authored_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="authored_exercise_phases",
    )
    provenance = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ("revision_id", "sequence_index", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "sequence_index"),
                name="exercise_phase_uniq_sequence",
            ),
            models.UniqueConstraint(
                fields=("revision", "code"),
                name="exercise_phase_uniq_code",
            ),
        ]

    def parent_revision(self):
        return self.revision

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        self.name = normalize_label(self.name)
        errors = {}
        if not self.code:
            errors["code"] = "La fase necessita un codi."
        if not self.name:
            errors["name"] = "La fase necessita un nom."
        if not self.description.strip():
            errors["description"] = "La fase necessita una descripció observable."
        if self.revision_id and self.authored_by_id != self.revision.exercise.catalog.owner_id:
            errors["authored_by"] = "La fase ha de pertànyer a l'autor del catàleg privat."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.revision.exercise} · {self.sequence_index}. {self.name}"


class ExercisePhaseAction(RevisionChildModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Acció principal"
        SUPPORTING = "supporting", "Acció de suport"

    class Laterality(models.TextChoices):
        BILATERAL = "bilateral", "Bilateral"
        LEFT = "left", "Esquerra"
        RIGHT = "right", "Dreta"
        ALTERNATING = "alternating", "Alternant"
        UNSPECIFIED = "unspecified", "No especificada"

    class VerificationState(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmat per l'autor"
        INFERRED = "inferred", "Inferit"
        PENDING = "pending", "Pendent de confirmar"

    phase = models.ForeignKey(ExercisePhase, on_delete=models.CASCADE, related_name="actions")
    action = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="exercise_phase_actions",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    laterality = models.CharField(
        max_length=20,
        choices=Laterality.choices,
        default=Laterality.UNSPECIFIED,
    )
    verification_state = models.CharField(
        max_length=20,
        choices=VerificationState.choices,
        default=VerificationState.PENDING,
    )
    rationale = models.TextField()
    provenance = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ("phase_id", "role", "action_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("phase", "action", "laterality"),
                name="exercise_phase_action_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("action", "role"), name="exercise_phase_action_idx"),
        ]

    def parent_revision(self):
        return self.phase.revision

    def clean(self):
        super().clean()
        errors = {}
        if self.action_id and self.action.kind != MotionConcept.Kind.JOINT_ACTION:
            errors["action"] = "La fase només pot enllaçar accions articulars."
        if not self.rationale.strip():
            errors["rationale"] = "Cal justificar la connexió cinemàtica."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.phase} → {self.action}"


class ExercisePhaseMuscleRole(RevisionChildModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Contribuïdor principal"
        SECONDARY = "secondary", "Contribuïdor secundari"
        STABILIZER = "stabilizer", "Estabilitzador"

    class ExpectedContraction(models.TextChoices):
        CONCENTRIC = "concentric", "Concèntrica esperada"
        ECCENTRIC = "eccentric", "Excèntrica esperada"
        ISOMETRIC = "isometric", "Isomètrica esperada"
        VARIABLE = "variable", "Variable segons execució"
        INDETERMINATE = "indeterminate", "No determinada"

    class VerificationState(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmat per l'autor"
        INFERRED = "inferred", "Inferit pel sistema"
        PENDING = "pending", "Pendent de confirmar"

    phase = models.ForeignKey(
        ExercisePhase,
        on_delete=models.CASCADE,
        related_name="muscle_roles",
    )
    muscle = models.ForeignKey(
        MotionConcept,
        on_delete=models.PROTECT,
        related_name="exercise_phase_muscle_roles",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    action_function = models.ForeignKey(
        MuscleActionFunction,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="exercise_phase_roles",
    )
    stabilization_function = models.ForeignKey(
        MuscleStabilizationFunction,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="exercise_phase_roles",
    )
    expected_contraction = models.CharField(
        max_length=20,
        choices=ExpectedContraction.choices,
        default=ExpectedContraction.INDETERMINATE,
    )
    verification_state = models.CharField(
        max_length=20,
        choices=VerificationState.choices,
        default=VerificationState.PENDING,
    )
    rationale = models.TextField()
    provenance = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ("phase_id", "role", "muscle_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("phase", "muscle", "role"),
                name="exercise_phase_muscle_uniq",
            ),
            models.CheckConstraint(
                check=(
                    Q(action_function__isnull=False, stabilization_function__isnull=True)
                    | Q(action_function__isnull=True, stabilization_function__isnull=False)
                ),
                name="exercise_muscle_exactly_one_basis",
            ),
        ]
        indexes = [
            models.Index(fields=("muscle", "role"), name="exercise_phase_muscle_idx"),
        ]

    def parent_revision(self):
        return self.phase.revision

    def clean(self):
        super().clean()
        errors = {}
        if self.muscle_id and self.muscle.kind != MotionConcept.Kind.MUSCLE:
            errors["muscle"] = "El rol muscular ha de referenciar un múscul."
        if bool(self.action_function_id) == bool(self.stabilization_function_id):
            errors["action_function"] = "Cal indicar exactament una base biomecànica."
        if self.action_function_id:
            if self.action_function.muscle_id != self.muscle_id:
                errors["action_function"] = "La funció d'acció ha de correspondre al múscul."
            if self.role == self.Role.STABILIZER:
                errors["role"] = "Un estabilitzador necessita una funció d'estabilització."
        if self.stabilization_function_id:
            if self.stabilization_function.muscle_id != self.muscle_id:
                errors["stabilization_function"] = (
                    "La funció estabilitzadora ha de correspondre al múscul."
                )
            if self.role != self.Role.STABILIZER:
                errors["role"] = "Una funció estabilitzadora necessita el rol estabilitzador."
            if self.expected_contraction not in {
                self.ExpectedContraction.ISOMETRIC,
                self.ExpectedContraction.VARIABLE,
                self.ExpectedContraction.INDETERMINATE,
            }:
                errors["expected_contraction"] = (
                    "Una estabilització no es pot fixar com a concèntrica o excèntrica aquí."
                )
        if not self.rationale.strip():
            errors["rationale"] = "Cal justificar el rol muscular."
        if not isinstance(self.provenance, dict):
            errors["provenance"] = "La procedència ha de ser un objecte JSON."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.phase} → {self.muscle} ({self.get_role_display()})"


class ExerciseEquipmentRequirement(RevisionChildModel):
    class Requirement(models.TextChoices):
        REQUIRED = "required", "Necessari"
        OPTIONAL = "optional", "Opcional"
        SUBSTITUTE = "substitute", "Alternativa"

    revision = models.ForeignKey(
        ExerciseRevision,
        on_delete=models.CASCADE,
        related_name="equipment_requirements",
    )
    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.PROTECT,
        related_name="exercise_requirements",
    )
    requirement = models.CharField(max_length=20, choices=Requirement.choices)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("revision_id", "requirement", "equipment_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "equipment"),
                name="exercise_equipment_requirement_uniq",
            ),
        ]

    def parent_revision(self):
        return self.revision

    def clean(self):
        super().clean()
        if self.revision_id and self.equipment_id:
            if self.equipment.catalog_id != self.revision.exercise.catalog_id:
                raise ValidationError(
                    {"equipment": "El material i l'exercici han de ser del mateix catàleg."}
                )

    def __str__(self):
        return f"{self.revision.exercise} · {self.equipment}"


class ExerciseObjective(RevisionChildModel):
    class Objective(models.TextChoices):
        GENERAL_STRENGTH = "strength", "Força general"
        MAX_STRENGTH = "max_strength", "Força màxima"
        HYPERTROPHY = "hypertrophy", "Hipertròfia"
        MUSCULAR_ENDURANCE = "muscular_endurance", "Resistència muscular"
        POWER = "power", "Potència"
        MOTOR_CONTROL = "motor_control", "Control motor"
        MOBILITY = "mobility", "Mobilitat"
        PREPARATION = "preparation", "Preparació o escalfament"

    class Priority(models.TextChoices):
        PRIMARY = "primary", "Principal"
        SECONDARY = "secondary", "Secundari"

    revision = models.ForeignKey(ExerciseRevision, on_delete=models.CASCADE, related_name="objectives")
    objective = models.CharField(max_length=30, choices=Objective.choices)
    priority = models.CharField(max_length=20, choices=Priority.choices)
    rationale = models.TextField()

    class Meta:
        ordering = ("revision_id", "priority", "objective", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "objective"),
                name="exercise_objective_uniq",
            ),
        ]

    def parent_revision(self):
        return self.revision

    def clean(self):
        super().clean()
        if not self.rationale.strip():
            raise ValidationError({"rationale": "Cal justificar l'objectiu de l'exercici."})

    def __str__(self):
        return f"{self.revision.exercise} · {self.get_objective_display()}"


class ExerciseConstraint(RevisionChildModel):
    class Kind(models.TextChoices):
        REQUIREMENT = "requirement", "Requisit d'execució"
        PRECAUTION = "precaution", "Precaució"
        LIMITATION = "limitation", "Limitació de l'exercici"

    class Severity(models.TextChoices):
        INFORMATION = "information", "Informativa"
        IMPORTANT = "important", "Important"
        CRITICAL = "critical", "Crítica"

    revision = models.ForeignKey(ExerciseRevision, on_delete=models.CASCADE, related_name="constraints")
    code = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    statement = models.TextField()
    rationale = models.TextField(blank=True, default="")

    class Meta:
        ordering = ("revision_id", "kind", "code", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "code"),
                name="exercise_constraint_uniq_code",
            ),
        ]

    def parent_revision(self):
        return self.revision

    def clean(self):
        super().clean()
        self.code = normalize_code(self.code)
        if not self.code:
            raise ValidationError({"code": "La restricció necessita un codi."
            })
        if not self.statement.strip():
            raise ValidationError({"statement": "La restricció necessita una descripció."})

    def __str__(self):
        return f"{self.revision.exercise} · {self.code}"


class ExercisePrescriptionGuideline(RevisionChildModel):
    """Professionally governed dosing envelope for one exercise revision.

    A guideline is deliberately a range, not a ready-made prescription. The
    training engine combines it with population baselines, athlete context and
    the coach request to create a concrete dose.
    """

    class PopulationStage(models.TextChoices):
        ALL = "all", "Totes"
        CHILD = "child", "Infància"
        ADOLESCENT = "adolescent", "Adolescència"
        ADULT = "adult", "Edat adulta"
        OLDER_ADULT = "older_adult", "Adult gran"

    class ExperienceLevel(models.TextChoices):
        ALL = "all", "Tots"
        NOVICE = "novice", "Inicial"
        INTERMEDIATE = "intermediate", "Intermedi"
        ADVANCED = "advanced", "Avançat"

    class BlockRole(models.TextChoices):
        ALL = "all", "Totes"
        PREPARATION = "preparation", "Preparació"
        MAIN = "main", "Principal"
        COMPLEMENTARY = "complementary", "Complementari"
        RECOVERY = "recovery", "Recuperació"
        ASSESSMENT = "assessment", "Avaluació"

    class DoseMode(models.TextChoices):
        REPETITIONS = "repetitions", "Repeticions"
        DURATION = "duration", "Durada"
        HOLD = "hold", "Manteniment"
        DISTANCE = "distance", "Distància"
        ASSISTED = "assisted", "Assistida"

    class EvidenceType(models.TextChoices):
        POSITION_STAND = "position_stand", "Posicionament professional"
        CONSENSUS = "consensus", "Consens"
        SYSTEMATIC_REVIEW = "systematic_review", "Revisió sistemàtica"
        PROFESSIONAL_STANDARD = "professional_standard", "Estàndard professional"
        EXPERT_REVIEW = "expert_review", "Revisió experta"
        OBSERVED_DATA = "observed_data", "Dades observades"

    revision = models.ForeignKey(
        ExerciseRevision,
        on_delete=models.CASCADE,
        related_name="prescription_guidelines",
    )
    population_stage = models.CharField(
        max_length=20, choices=PopulationStage.choices, default=PopulationStage.ALL
    )
    experience_level = models.CharField(
        max_length=20, choices=ExperienceLevel.choices, default=ExperienceLevel.ALL
    )
    objective = models.CharField(
        max_length=30, choices=ExerciseObjective.Objective.choices
    )
    block_role = models.CharField(
        max_length=20, choices=BlockRole.choices, default=BlockRole.ALL
    )
    dose_mode = models.CharField(max_length=20, choices=DoseMode.choices)
    min_sets = models.PositiveSmallIntegerField(default=1)
    default_sets = models.PositiveSmallIntegerField(default=2)
    max_sets = models.PositiveSmallIntegerField(default=3)
    min_repetitions = models.PositiveSmallIntegerField(null=True, blank=True)
    default_repetitions = models.PositiveSmallIntegerField(null=True, blank=True)
    max_repetitions = models.PositiveSmallIntegerField(null=True, blank=True)
    min_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    default_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    max_duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    min_rest_seconds = models.PositiveSmallIntegerField(default=0)
    default_rest_seconds = models.PositiveSmallIntegerField(default=60)
    max_rest_seconds = models.PositiveSmallIntegerField(default=180)
    min_rpe = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(10)),
    )
    max_rpe = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(10)),
    )
    setup_duration_seconds = models.PositiveSmallIntegerField(default=20)
    seconds_per_repetition = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=(MinValueValidator(0.1),),
    )
    mechanical_impact = models.DecimalField(
        max_digits=2, decimal_places=1, default=1, validators=(MinValueValidator(0), MaxValueValidator(5))
    )
    neuromuscular_load = models.DecimalField(
        max_digits=2, decimal_places=1, default=1, validators=(MinValueValidator(0), MaxValueValidator(5))
    )
    metabolic_load = models.DecimalField(
        max_digits=2, decimal_places=1, default=1, validators=(MinValueValidator(0), MaxValueValidator(5))
    )
    coordinative_load = models.DecimalField(
        max_digits=2, decimal_places=1, default=1, validators=(MinValueValidator(0), MaxValueValidator(5))
    )
    quality_stop_rule = models.TextField(blank=True, default="")
    evidence_type = models.CharField(max_length=30, choices=EvidenceType.choices)
    source_title = models.CharField(max_length=240)
    source_url = models.URLField(blank=True, default="")
    source_year = models.PositiveSmallIntegerField(null=True, blank=True)
    rationale = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = (
            "revision_id",
            "population_stage",
            "experience_level",
            "objective",
            "block_role",
        )
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "revision",
                    "population_stage",
                    "experience_level",
                    "objective",
                    "block_role",
                    "dose_mode",
                ),
                name="exercise_prescription_guideline_uniq",
            )
        ]

    def parent_revision(self):
        return self.revision

    def clean(self):
        super().clean()
        errors = {}

        def ordered(minimum, default, maximum, field):
            values = (minimum, default, maximum)
            present = [value is not None for value in values]
            if any(present) and not all(present):
                errors[field] = "El rang necessita mínim, valor habitual i màxim."
            elif all(present) and not minimum <= default <= maximum:
                errors[field] = "El rang ha de complir mínim ≤ habitual ≤ màxim."

        ordered(self.min_sets, self.default_sets, self.max_sets, "default_sets")
        ordered(
            self.min_repetitions,
            self.default_repetitions,
            self.max_repetitions,
            "default_repetitions",
        )
        ordered(
            self.min_duration_seconds,
            self.default_duration_seconds,
            self.max_duration_seconds,
            "default_duration_seconds",
        )
        ordered(
            self.min_rest_seconds,
            self.default_rest_seconds,
            self.max_rest_seconds,
            "default_rest_seconds",
        )
        if self.dose_mode == self.DoseMode.REPETITIONS and self.default_repetitions is None:
            errors["default_repetitions"] = "La dosi per repeticions necessita un rang."
        if self.dose_mode in {self.DoseMode.DURATION, self.DoseMode.HOLD} and self.default_duration_seconds is None:
            errors["default_duration_seconds"] = "La dosi temporal necessita un rang."
        if self.min_rpe is not None and self.max_rpe is not None and self.min_rpe > self.max_rpe:
            errors["max_rpe"] = "L'RPE màxim no pot ser inferior al mínim."
        if not self.source_title.strip():
            errors["source_title"] = "La guideline necessita una font identificable."
        if not self.rationale.strip():
            errors["rationale"] = "Cal explicar l'aplicabilitat de la font."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.revision} · {self.get_population_stage_display()} · {self.get_objective_display()}"


class ExerciseGap(models.Model):
    """A durable completeness issue; proposed content is stored separately."""

    class Severity(models.TextChoices):
        REQUIRED = "required", "Obligatori"
        RECOMMENDED = "recommended", "Recomanat"

    class Status(models.TextChoices):
        OPEN = "open", "Obert"
        PROPOSED = "proposed", "Amb proposta"
        RESOLVED = "resolved", "Resolt"
        DISMISSED = "dismissed", "Descartat"

    class DetectedBy(models.TextChoices):
        SYSTEM = "system", "Validador del sistema"
        LLM = "llm", "Model de llenguatge"
        HUMAN = "human", "Persona"

    revision = models.ForeignKey(ExerciseRevision, on_delete=models.CASCADE, related_name="gaps")
    requirement_code = models.CharField(max_length=100)
    field_path = models.CharField(max_length=220)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    detected_by = models.CharField(max_length=20, choices=DetectedBy.choices)
    description = models.TextField()
    schema_version = models.CharField(max_length=60, default="exercise_completeness_v1")
    resolution_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("revision_id", "severity", "requirement_code", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("revision", "requirement_code", "schema_version"),
                name="exercise_gap_uniq_requirement",
            ),
        ]
        indexes = [
            models.Index(fields=("revision", "status"), name="exercise_gap_status_idx"),
        ]

    def clean(self):
        super().clean()
        self.requirement_code = normalize_code(self.requirement_code)
        if not self.requirement_code:
            raise ValidationError({"requirement_code": "El buit necessita un codi estable."})
        if not self.field_path.strip():
            raise ValidationError({"field_path": "El buit necessita una ubicació estructurada."})
        if not self.description.strip():
            raise ValidationError({"description": "El buit necessita una explicació."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.revision} · {self.requirement_code}"


class ExerciseChangeProposal(models.Model):
    class Origin(models.TextChoices):
        HUMAN = "human", "Persona"
        LLM = "llm", "Model de llenguatge"
        SYSTEM = "system", "Sistema"

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposada"
        ACCEPTED = "accepted", "Acceptada"
        REJECTED = "rejected", "Rebutjada"
        APPLIED = "applied", "Aplicada"

    revision = models.ForeignKey(
        ExerciseRevision,
        on_delete=models.CASCADE,
        related_name="change_proposals",
    )
    origin = models.CharField(max_length=20, choices=Origin.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    rationale = models.TextField()
    model_name = models.CharField(max_length=120, blank=True, default="")
    created_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="exercise_change_proposals",
    )
    reviewed_by = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_exercise_change_proposals",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("revision", "status"), name="exercise_proposal_status_idx"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not self.rationale.strip():
            errors["rationale"] = "La proposta necessita una justificació."
        if self.revision_id and self.created_by_id != self.revision.exercise.catalog.owner_id:
            errors["created_by"] = "La proposta ha de pertànyer al propietari del catàleg."
        if self.status != self.Status.PROPOSED and not self.reviewed_by_id:
            errors["reviewed_by"] = "Una proposta decidida necessita un revisor."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.revision} · {self.get_status_display()}"


class ExerciseProposalItem(models.Model):
    class Operation(models.TextChoices):
        ADD = "add", "Afegir"
        REPLACE = "replace", "Substituir"
        REMOVE = "remove", "Retirar"
        LINK = "link", "Crear connexió"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendent"
        ACCEPTED = "accepted", "Acceptat"
        REJECTED = "rejected", "Rebutjat"
        APPLIED = "applied", "Aplicat"

    proposal = models.ForeignKey(
        ExerciseChangeProposal,
        on_delete=models.CASCADE,
        related_name="items",
    )
    resolves_gap = models.ForeignKey(
        ExerciseGap,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="proposal_items",
    )
    operation = models.CharField(max_length=20, choices=Operation.choices)
    target_path = models.CharField(max_length=220)
    proposed_value = models.JSONField()
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
    )
    evidence = models.JSONField(blank=True, default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("proposal_id", "id")
        indexes = [
            models.Index(fields=("proposal", "status"), name="exercise_proposal_item_idx"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not self.target_path.strip():
            errors["target_path"] = "La proposta necessita un destí estructurat."
        if not isinstance(self.evidence, dict):
            errors["evidence"] = "L'evidència de proposta ha de ser un objecte JSON."
        if self.resolves_gap_id and self.resolves_gap.revision_id != self.proposal.revision_id:
            errors["resolves_gap"] = "El buit i la proposta han de pertànyer a la mateixa revisió."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.proposal} · {self.operation} {self.target_path}"
