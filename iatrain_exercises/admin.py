from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError

from iatrain_motion.models import EditorialStatus

from .editorial import transition_exercise_revision
from .models import (
    Equipment,
    Exercise,
    ExerciseCatalog,
    ExerciseChangeProposal,
    ExerciseConstraint,
    ExerciseEquipmentRequirement,
    ExerciseGap,
    ExerciseObjective,
    ExercisePhase,
    ExercisePhaseAction,
    ExercisePhaseMuscleRole,
    ExercisePrescriptionGuideline,
    ExerciseProposalItem,
    ExerciseRevision,
)


class DraftChildInline(admin.TabularInline):
    extra = 0

    def has_delete_permission(self, request, obj=None):
        return not obj or obj.editorial_status == EditorialStatus.DRAFT


class PhaseInline(DraftChildInline):
    model = ExercisePhase
    autocomplete_fields = ("authored_by",)


class ObjectiveInline(DraftChildInline):
    model = ExerciseObjective


class EquipmentRequirementInline(DraftChildInline):
    model = ExerciseEquipmentRequirement
    autocomplete_fields = ("equipment",)


class ConstraintInline(DraftChildInline):
    model = ExerciseConstraint


class PrescriptionGuidelineInline(DraftChildInline):
    model = ExercisePrescriptionGuideline


class PhaseActionInline(admin.TabularInline):
    model = ExercisePhaseAction
    extra = 0
    autocomplete_fields = ("action",)


class PhaseMuscleInline(admin.TabularInline):
    model = ExercisePhaseMuscleRole
    extra = 0
    autocomplete_fields = ("muscle", "action_function", "stabilization_function")


class ProposalItemInline(admin.TabularInline):
    model = ExerciseProposalItem
    extra = 0
    autocomplete_fields = ("resolves_gap",)


@admin.register(ExerciseCatalog)
class ExerciseCatalogAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "owner", "kind", "is_active", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("code", "name", "owner__first_name", "owner__last_name")
    autocomplete_fields = ("owner",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "catalog", "category", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("code", "name", "catalog__name")
    autocomplete_fields = ("catalog",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "catalog", "parent", "is_active")
    list_filter = ("kind", "is_active", "catalog")
    search_fields = ("code", "name", "catalog__name")
    autocomplete_fields = ("catalog", "parent", "created_by")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExerciseRevision)
class ExerciseRevisionAdmin(admin.ModelAdmin):
    list_display = (
        "exercise", "revision_number", "movement_pattern", "modality", "difficulty",
        "editorial_status", "updated_at",
    )
    list_filter = (
        "editorial_status", "modality", "movement_pattern", "difficulty", "kinetic_chain",
    )
    search_fields = ("exercise__code", "exercise__name", "description", "coaching_cues")
    autocomplete_fields = ("exercise", "authored_by", "supersedes")
    readonly_fields = (
        "editorial_status", "last_validated_by", "last_validated_at", "created_at", "updated_at",
    )
    inlines = (
        PhaseInline,
        ObjectiveInline,
        EquipmentRequirementInline,
        ConstraintInline,
        PrescriptionGuidelineInline,
    )
    actions = ("validate_selected", "retire_selected", "reopen_retired_selected")

    def _transition(self, request, queryset, target):
        changed = 0
        for revision in queryset:
            try:
                result = transition_exercise_revision(
                    user=request.user,
                    revision=revision,
                    target_status=target,
                )
            except (ValidationError, PermissionDenied) as exc:
                self.message_user(request, f"{revision}: {exc}", level=messages.ERROR)
                continue
            changed += result.previous_status != target
        if changed:
            self.message_user(request, f"Revisions actualitzades: {changed}.", messages.SUCCESS)

    @admin.action(description="Validar la selecció")
    def validate_selected(self, request, queryset):
        self._transition(request, queryset, EditorialStatus.VALIDATED)

    @admin.action(description="Retirar la selecció")
    def retire_selected(self, request, queryset):
        self._transition(request, queryset, EditorialStatus.RETIRED)

    @admin.action(description="Reobrir revisions retirades")
    def reopen_retired_selected(self, request, queryset):
        self._transition(request, queryset, EditorialStatus.DRAFT)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExercisePhase)
class ExercisePhaseAdmin(admin.ModelAdmin):
    list_display = ("revision", "sequence_index", "code", "name", "intent", "is_key_phase")
    list_filter = ("phase_type", "intent", "is_key_phase")
    search_fields = ("revision__exercise__name", "code", "name", "description")
    autocomplete_fields = ("revision", "authored_by")
    inlines = (PhaseActionInline, PhaseMuscleInline)


@admin.register(ExercisePhaseAction)
class ExercisePhaseActionAdmin(admin.ModelAdmin):
    list_display = ("phase", "action", "role", "laterality", "verification_state")
    list_filter = ("role", "laterality", "verification_state")
    search_fields = ("phase__revision__exercise__name", "action__code", "action__name")
    autocomplete_fields = ("phase", "action")


@admin.register(ExercisePhaseMuscleRole)
class ExercisePhaseMuscleRoleAdmin(admin.ModelAdmin):
    list_display = (
        "phase", "muscle", "role", "expected_contraction", "verification_state",
    )
    list_filter = ("role", "expected_contraction", "verification_state")
    search_fields = ("phase__revision__exercise__name", "muscle__code", "muscle__name")
    autocomplete_fields = ("phase", "muscle", "action_function", "stabilization_function")


@admin.register(ExercisePrescriptionGuideline)
class ExercisePrescriptionGuidelineAdmin(admin.ModelAdmin):
    list_display = (
        "revision",
        "population_stage",
        "experience_level",
        "objective",
        "block_role",
        "dose_mode",
        "is_active",
    )
    list_filter = (
        "population_stage",
        "experience_level",
        "objective",
        "block_role",
        "evidence_type",
        "is_active",
    )
    search_fields = ("revision__exercise__name", "source_title", "rationale")
    autocomplete_fields = ("revision",)


@admin.register(ExerciseGap)
class ExerciseGapAdmin(admin.ModelAdmin):
    list_display = ("revision", "requirement_code", "severity", "status", "detected_by")
    list_filter = ("severity", "status", "detected_by", "schema_version")
    search_fields = ("revision__exercise__name", "requirement_code", "description", "field_path")
    autocomplete_fields = ("revision",)


@admin.register(ExerciseChangeProposal)
class ExerciseChangeProposalAdmin(admin.ModelAdmin):
    list_display = ("revision", "origin", "status", "model_name", "created_by", "created_at")
    list_filter = ("origin", "status")
    search_fields = ("revision__exercise__name", "rationale", "model_name")
    autocomplete_fields = ("revision", "created_by", "reviewed_by")
    inlines = (ProposalItemInline,)
