from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from iatrain_motion.models import EditorialStatus

from .editorial import (
    transition_biomechanical_context,
    transition_muscle_action_function,
    transition_muscle_stabilization_function,
)
from .models import (
    BiomechanicalContext,
    ContextAngleConstraint,
    EvidenceReference,
    MuscleActionFunction,
    MuscleActionFunctionEvidence,
    MuscleStabilizationEvidence,
    MuscleStabilizationFunction,
)


class EditorialActionsMixin:
    actions = ("validate_selected", "reopen_selected", "retire_selected")
    transition_service = None
    transition_argument = None

    def _transition_selected(self, request, queryset, target_status):
        changed = 0
        for instance in queryset:
            try:
                transition = self.transition_service(
                    user=request.user,
                    **{self.transition_argument: instance},
                    target_status=target_status,
                )
            except ValidationError as exc:
                self.message_user(request, f"{instance}: {exc}", level=messages.ERROR)
                continue
            changed += transition.previous_status != target_status
        if changed:
            self.message_user(request, f"Registres actualitzats: {changed}.", level=messages.SUCCESS)

    @admin.action(description="Validar la selecció")
    def validate_selected(self, request, queryset):
        self._transition_selected(request, queryset, EditorialStatus.VALIDATED)

    @admin.action(description="Reobrir la selecció")
    def reopen_selected(self, request, queryset):
        self._transition_selected(request, queryset, EditorialStatus.DRAFT)

    @admin.action(description="Retirar la selecció")
    def retire_selected(self, request, queryset):
        self._transition_selected(request, queryset, EditorialStatus.RETIRED)


class EvidenceInline(admin.TabularInline):
    extra = 0
    autocomplete_fields = ("evidence",)

    def has_delete_permission(self, request, obj=None):
        return not obj or obj.editorial_status == EditorialStatus.DRAFT


class MuscleActionEvidenceInline(EvidenceInline):
    model = MuscleActionFunctionEvidence


class MuscleStabilizationEvidenceInline(EvidenceInline):
    model = MuscleStabilizationEvidence


class AngleConstraintInline(admin.TabularInline):
    model = ContextAngleConstraint
    extra = 0
    autocomplete_fields = ("angle_definition", "authored_by")

    def has_delete_permission(self, request, obj=None):
        return not obj or obj.editorial_status == EditorialStatus.DRAFT


@admin.register(EvidenceReference)
class EvidenceReferenceAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "source_type", "identifier_type", "updated_at")
    list_filter = ("source_type", "identifier_type")
    search_fields = ("code", "title", "identifier", "citation")
    autocomplete_fields = ("authored_by",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BiomechanicalContext)
class BiomechanicalContextAdmin(EditorialActionsMixin, admin.ModelAdmin):
    transition_service = staticmethod(transition_biomechanical_context)
    transition_argument = "context"
    list_display = ("code", "name", "kinetic_chain", "editorial_status", "updated_at")
    list_filter = ("kinetic_chain", "editorial_status")
    search_fields = ("code", "name", "description")
    autocomplete_fields = ("authored_by",)
    inlines = (AngleConstraintInline,)
    readonly_fields = (
        "editorial_status", "last_validated_by", "last_validated_at", "created_at", "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False


class GovernedFunctionAdmin(EditorialActionsMixin, admin.ModelAdmin):
    readonly_fields = (
        "editorial_status", "last_validated_by", "last_validated_at", "created_at", "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MuscleActionFunction)
class MuscleActionFunctionAdmin(GovernedFunctionAdmin):
    transition_service = staticmethod(transition_muscle_action_function)
    transition_argument = "function"
    list_display = (
        "code", "muscle", "action", "contribution_class", "context", "editorial_status",
    )
    list_filter = ("editorial_status", "contribution_class", "context")
    search_fields = ("code", "muscle__name", "action__name", "statement")
    autocomplete_fields = ("muscle", "action", "context", "supersedes", "authored_by")
    inlines = (MuscleActionEvidenceInline,)


@admin.register(MuscleStabilizationFunction)
class MuscleStabilizationFunctionAdmin(GovernedFunctionAdmin):
    transition_service = staticmethod(transition_muscle_stabilization_function)
    transition_argument = "function"
    list_display = (
        "code", "muscle", "target_joint", "target_segment", "stabilization_type",
        "editorial_status",
    )
    list_filter = ("editorial_status", "stabilization_type", "context")
    search_fields = ("code", "muscle__name", "statement")
    autocomplete_fields = (
        "muscle", "target_joint", "target_segment", "context", "supersedes", "authored_by",
    )
    inlines = (MuscleStabilizationEvidenceInline,)
