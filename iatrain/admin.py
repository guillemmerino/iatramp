from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError

from .editorial import transition_element_rotation

from .models import (
    AthleteCondition,
    AthleteInsight,
    AthleteInsightEvidence,
    AthleteMeasurement,
    AthleteObservation,
    AthleteProfile,
    AthleteSportProfile,
    BlockGenerationRun,
    BlockParticipantAssignment,
    CoachAthleteRelation,
    CoachProfile,
    ElementNotation,
    ElementRotation,
    ElementRotationSegment,
    Gym,
    GymEquipment,
    GymOrganization,
    KnowledgeConcept,
    KnowledgeEditorialEvent,
    KnowledgeRelation,
    TrainingContext,
    TrainingBlock,
    TrainingGroup,
    TrainingGroupMembership,
    TrainingItemResult,
    TrainingSession,
    TrainingSessionExecution,
    TrainingSessionItem,
    TrainingSessionRevision,
    SessionAttendance,
    SessionGoal,
    SessionItemAlternative,
    SessionItemAthleteAdjustment,
    SessionParticipantPlan,
    PhysicalExercisePrescription,
)


class SessionParticipantPlanInline(admin.TabularInline):
    model = SessionParticipantPlan
    extra = 0
    autocomplete_fields = ("athlete_profile",)


class SessionGoalInline(admin.TabularInline):
    model = SessionGoal
    extra = 0


@admin.register(BlockGenerationRun)
class BlockGenerationRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "session_revision",
        "status",
        "model_name",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "model_name", "engine_version")
    search_fields = ("prompt", "session_revision__title", "created_by__first_name", "created_by__last_name")
    autocomplete_fields = ("session_revision", "created_by", "parent_run", "applied_block")
    readonly_fields = (
        "interpretation_payload",
        "request_payload",
        "proposal_payload",
        "decision_payload",
        "coach_decisions",
        "source_references",
        "created_at",
        "updated_at",
    )


@admin.register(SessionParticipantPlan)
class SessionParticipantPlanAdmin(admin.ModelAdmin):
    list_display = ("session_revision", "athlete_profile", "expected_participation")
    search_fields = (
        "session_revision__title",
        "athlete_profile__person__first_name",
        "athlete_profile__person__last_name",
    )
    autocomplete_fields = ("session_revision", "athlete_profile")


@admin.register(SessionGoal)
class SessionGoalAdmin(admin.ModelAdmin):
    list_display = ("session_revision", "domain", "code", "priority")
    list_filter = ("domain", "priority", "source")
    search_fields = ("code", "description", "session_revision__title")
    autocomplete_fields = ("session_revision",)


class TrainingBlockInline(admin.TabularInline):
    model = TrainingBlock
    extra = 0
    fields = (
        "sequence_index",
        "name",
        "block_role",
        "domain",
        "execution_mode",
        "planned_duration_minutes",
    )


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "scheduled_start",
        "organization",
        "discipline",
        "session_scope",
        "responsible_coach",
        "lifecycle_status",
    )
    list_filter = ("lifecycle_status", "discipline", "session_scope", "organization")
    search_fields = ("organization__name", "training_group__name")
    autocomplete_fields = (
        "organization",
        "gym",
        "training_group",
        "responsible_coach",
        "created_by",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(TrainingSessionRevision)
class TrainingSessionRevisionAdmin(admin.ModelAdmin):
    list_display = ("title", "session", "revision_number", "status", "updated_at")
    list_filter = ("status", "creation_origin")
    search_fields = ("title", "general_objective", "session__organization__name")
    autocomplete_fields = ("session", "supersedes", "created_by", "approved_by")
    readonly_fields = ("approved_by", "approved_at", "created_at", "updated_at")
    inlines = (SessionParticipantPlanInline, SessionGoalInline, TrainingBlockInline)


@admin.register(TrainingBlock)
class TrainingBlockAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "session_revision",
        "sequence_index",
        "block_role",
        "domain",
        "planned_duration_minutes",
    )
    list_filter = ("block_role", "domain", "execution_mode")
    search_fields = ("name", "objective", "session_revision__title")
    autocomplete_fields = ("session_revision",)


@admin.register(BlockParticipantAssignment)
class BlockParticipantAssignmentAdmin(admin.ModelAdmin):
    list_display = ("block", "participant_plan", "mode")
    list_filter = ("mode",)
    autocomplete_fields = ("block", "participant_plan")


@admin.register(TrainingSessionItem)
class TrainingSessionItemAdmin(admin.ModelAdmin):
    list_display = ("title", "block", "sequence_index", "item_type", "is_optional")
    list_filter = ("item_type", "is_optional")
    search_fields = ("title", "instructions", "block__name")
    autocomplete_fields = ("block",)


@admin.register(PhysicalExercisePrescription)
class PhysicalExercisePrescriptionAdmin(admin.ModelAdmin):
    list_display = ("session_item", "exercise_revision", "dose_mode", "sets")
    list_filter = ("dose_mode", "intensity_metric")
    autocomplete_fields = ("session_item", "exercise_revision")


@admin.register(SessionItemAlternative)
class SessionItemAlternativeAdmin(admin.ModelAdmin):
    list_display = ("session_item", "exercise_revision", "priority", "trigger")
    list_filter = ("trigger",)
    autocomplete_fields = ("session_item", "exercise_revision")


@admin.register(SessionItemAthleteAdjustment)
class SessionItemAthleteAdjustmentAdmin(admin.ModelAdmin):
    list_display = (
        "session_item",
        "participant_plan",
        "action",
        "replacement_exercise_revision",
    )
    list_filter = ("action",)
    autocomplete_fields = (
        "session_item",
        "participant_plan",
        "replacement_exercise_revision",
    )


class SessionAttendanceInline(admin.TabularInline):
    model = SessionAttendance
    extra = 0
    autocomplete_fields = ("athlete_profile",)


@admin.register(TrainingSessionExecution)
class TrainingSessionExecutionAdmin(admin.ModelAdmin):
    list_display = ("session", "approved_revision", "status", "started_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("session__organization__name", "approved_revision__title")
    autocomplete_fields = ("session", "approved_revision", "supervised_by")
    readonly_fields = ("created_at", "updated_at")
    inlines = (SessionAttendanceInline,)


@admin.register(TrainingItemResult)
class TrainingItemResultAdmin(admin.ModelAdmin):
    list_display = (
        "execution",
        "session_item",
        "athlete_profile",
        "completion_status",
        "recorded_at",
    )
    list_filter = ("completion_status", "pain_response")
    autocomplete_fields = (
        "execution",
        "session_item",
        "athlete_profile",
        "exercise_revision_performed",
        "recorded_by",
    )


@admin.register(AthleteProfile)
class AthleteProfileAdmin(admin.ModelAdmin):
    list_display = ("person", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("person__first_name", "person__last_name", "person__preferred_name")
    autocomplete_fields = ("person",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(AthleteSportProfile)
class AthleteSportProfileAdmin(admin.ModelAdmin):
    list_display = (
        "athlete_profile",
        "discipline",
        "level_code",
        "preferred_laterality",
        "is_active",
    )
    list_filter = ("discipline", "preferred_laterality", "is_active")
    search_fields = (
        "athlete_profile__person__first_name",
        "athlete_profile__person__last_name",
        "level_code",
    )
    autocomplete_fields = ("athlete_profile", "updated_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AthleteMeasurement)
class AthleteMeasurementAdmin(admin.ModelAdmin):
    list_display = (
        "athlete_profile",
        "metric_label",
        "value",
        "unit",
        "side",
        "measured_at",
        "status",
    )
    list_filter = ("domain", "source", "status", "side", "organization")
    search_fields = (
        "athlete_profile__person__first_name",
        "athlete_profile__person__last_name",
        "metric_code",
        "metric_label",
    )
    autocomplete_fields = (
        "athlete_profile",
        "organization",
        "recorded_by",
        "supersedes",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "measured_at"


@admin.register(AthleteCondition)
class AthleteConditionAdmin(admin.ModelAdmin):
    list_display = (
        "athlete_profile",
        "title",
        "category",
        "training_impact",
        "status",
        "started_at",
    )
    list_filter = ("category", "training_impact", "status", "organization")
    search_fields = (
        "athlete_profile__person__first_name",
        "athlete_profile__person__last_name",
        "title",
        "narrative",
        "evidence",
    )
    autocomplete_fields = (
        "athlete_profile",
        "organization",
        "body_region",
        "recorded_by",
        "confirmed_by",
        "supersedes",
    )
    readonly_fields = ("confirmed_by", "confirmed_at", "created_at", "updated_at")
    date_hierarchy = "started_at"


class AthleteInsightEvidenceInline(admin.TabularInline):
    model = AthleteInsightEvidence
    extra = 0
    fields = (
        "observation",
        "measurement",
        "condition",
        "training_item_result",
        "contribution",
    )


@admin.register(AthleteInsight)
class AthleteInsightAdmin(admin.ModelAdmin):
    list_display = (
        "athlete_profile",
        "kind",
        "status",
        "confidence",
        "model_name",
        "created_at",
    )
    list_filter = ("kind", "status", "organization", "model_name")
    search_fields = (
        "athlete_profile__person__first_name",
        "athlete_profile__person__last_name",
        "statement",
        "rationale",
    )
    autocomplete_fields = (
        "athlete_profile",
        "organization",
        "triggered_by",
        "confirmed_by",
    )
    readonly_fields = ("confirmed_by", "confirmed_at", "created_at", "updated_at")
    inlines = (AthleteInsightEvidenceInline,)


@admin.register(CoachProfile)
class CoachProfileAdmin(admin.ModelAdmin):
    list_display = ("person", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("person__first_name", "person__last_name", "person__preferred_name")
    autocomplete_fields = ("person",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(CoachAthleteRelation)
class CoachAthleteRelationAdmin(admin.ModelAdmin):
    list_display = (
        "coach_profile",
        "athlete_profile",
        "organization",
        "function",
        "is_active",
        "can_edit_training",
        "can_view_health_data",
    )
    list_filter = ("function", "is_active", "organization")
    search_fields = (
        "coach_profile__person__first_name",
        "coach_profile__person__last_name",
        "athlete_profile__person__first_name",
        "athlete_profile__person__last_name",
    )
    autocomplete_fields = ("coach_profile", "athlete_profile", "organization")
    readonly_fields = ("created_at", "updated_at")


class TrainingGroupMembershipInline(admin.TabularInline):
    model = TrainingGroupMembership
    extra = 0
    autocomplete_fields = ("athlete_profile",)
    fields = ("athlete_profile", "start_date", "end_date", "is_active", "notes")


@admin.register(TrainingGroup)
class TrainingGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active", "updated_at")
    list_filter = ("is_active", "organization")
    search_fields = (
        "name",
        "description",
        "organization__name",
        "memberships__athlete_profile__person__first_name",
        "memberships__athlete_profile__person__last_name",
    )
    autocomplete_fields = ("organization", "managing_coaches")
    readonly_fields = ("created_at", "updated_at")
    inlines = (TrainingGroupMembershipInline,)


@admin.register(TrainingGroupMembership)
class TrainingGroupMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "training_group",
        "athlete_profile",
        "start_date",
        "end_date",
        "is_active",
    )
    list_filter = ("is_active", "training_group__organization", "training_group")
    search_fields = (
        "training_group__name",
        "athlete_profile__person__first_name",
        "athlete_profile__person__last_name",
        "notes",
    )
    autocomplete_fields = ("training_group", "athlete_profile")
    readonly_fields = ("created_at", "updated_at")


class GymOrganizationInline(admin.TabularInline):
    model = GymOrganization
    extra = 0
    autocomplete_fields = ("organization",)


class GymEquipmentInline(admin.TabularInline):
    model = GymEquipment
    extra = 0
    fields = ("name", "equipment_type", "quantity", "availability", "notes")


@admin.register(Gym)
class GymAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "is_active", "updated_at")
    list_filter = ("is_active", "organizations")
    search_fields = ("name", "location", "notes", "organizations__name")
    autocomplete_fields = ("created_by",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (GymOrganizationInline, GymEquipmentInline)


@admin.register(GymEquipment)
class GymEquipmentAdmin(admin.ModelAdmin):
    list_display = ("name", "gym", "equipment_type", "quantity", "availability")
    list_filter = ("equipment_type", "availability", "gym")
    search_fields = ("name", "gym__name", "notes")
    autocomplete_fields = ("gym",)
    readonly_fields = ("created_at", "updated_at")


class OutgoingKnowledgeRelationInline(admin.TabularInline):
    model = KnowledgeRelation
    fk_name = "source"
    extra = 0
    can_delete = False
    show_change_link = True
    autocomplete_fields = ("target", "authored_by")
    fields = ("relation_type", "target", "editorial_status", "authored_by", "rationale")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(TrainingContext)
class TrainingContextAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "discipline",
        "responsible_coach",
        "organization",
        "status",
        "valid_from",
        "valid_until",
    )
    list_filter = ("status", "discipline", "organization")
    search_fields = (
        "name",
        "purpose",
        "responsible_coach__first_name",
        "responsible_coach__last_name",
        "athletes__first_name",
        "athletes__last_name",
    )
    autocomplete_fields = ("responsible_coach", "organization", "athletes")
    readonly_fields = ("created_at", "updated_at")


@admin.register(KnowledgeConcept)
class KnowledgeConceptAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "discipline", "editorial_status", "authored_by", "updated_at")
    list_filter = ("editorial_status", "kind", "discipline")
    search_fields = ("name", "description", "kind", "discipline")
    autocomplete_fields = ("authored_by",)
    readonly_fields = (
        "editorial_status",
        "last_validated_by",
        "last_validated_at",
        "created_at",
        "updated_at",
    )
    inlines = (OutgoingKnowledgeRelationInline,)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.editorial_status != KnowledgeConcept.EditorialStatus.DRAFT:
            fields.extend(("name", "description", "kind", "discipline", "authored_by", "attributes"))
        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(KnowledgeRelation)
class KnowledgeRelationAdmin(admin.ModelAdmin):
    list_display = ("source", "relation_type", "target", "editorial_status", "authored_by", "updated_at")
    list_filter = ("editorial_status", "relation_type", "source__discipline")
    search_fields = ("source__name", "target__name", "relation_type", "rationale")
    autocomplete_fields = ("source", "target", "authored_by")
    readonly_fields = (
        "editorial_status",
        "last_validated_by",
        "last_validated_at",
        "created_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.editorial_status != KnowledgeRelation.EditorialStatus.DRAFT:
            fields.extend(("source", "target", "relation_type", "rationale", "authored_by"))
        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(KnowledgeEditorialEvent)
class KnowledgeEditorialEventAdmin(admin.ModelAdmin):
    list_display = (
        "target_repr",
        "target_model",
        "from_status",
        "to_status",
        "decided_by",
        "created_at",
    )
    list_filter = ("target_model", "from_status", "to_status")
    search_fields = ("target_repr", "reason", "decided_by__first_name", "decided_by__last_name")
    readonly_fields = (
        "target_model",
        "target_id",
        "target_repr",
        "from_status",
        "to_status",
        "decided_by",
        "reason",
        "snapshot",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False


class ElementRotationSegmentInline(admin.TabularInline):
    model = ElementRotationSegment
    extra = 0

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.editorial_status != KnowledgeConcept.EditorialStatus.DRAFT:
            return ("sequence_index", "longitudinal_half_turns")
        return ()

    def has_add_permission(self, request, obj=None):
        return not obj or obj.editorial_status == KnowledgeConcept.EditorialStatus.DRAFT

    def has_delete_permission(self, request, obj=None):
        return not obj or obj.editorial_status == KnowledgeConcept.EditorialStatus.DRAFT


class ElementNotationInline(admin.TabularInline):
    model = ElementNotation
    fk_name = "rotation"
    extra = 0
    fields = (
        "raw_notation",
        "normalized_notation",
        "parse_status",
        "is_abbreviated",
        "direction_source",
        "position_source",
    )
    readonly_fields = fields
    can_delete = False


@admin.register(ElementRotation)
class ElementRotationAdmin(admin.ModelAdmin):
    list_display = (
        "element",
        "transverse_quarters",
        "transverse_direction",
        "editorial_status",
        "authored_by",
        "updated_at",
    )
    list_filter = ("editorial_status", "transverse_direction", "transverse_quarters")
    search_fields = ("element__name",)
    autocomplete_fields = ("element", "authored_by")
    readonly_fields = (
        "editorial_status",
        "last_validated_by",
        "last_validated_at",
        "created_at",
        "updated_at",
    )
    inlines = (ElementRotationSegmentInline, ElementNotationInline)
    actions = ("validate_rotations", "reopen_rotations", "retire_rotations")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.editorial_status != KnowledgeConcept.EditorialStatus.DRAFT:
            fields.extend(
                (
                    "element",
                    "transverse_quarters",
                    "transverse_direction",
                    "authored_by",
                    "provenance",
                )
            )
        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        return False

    def _transition_selected(self, request, queryset, target_status):
        changed = 0
        for rotation in queryset:
            try:
                transition = transition_element_rotation(
                    user=request.user,
                    rotation=rotation,
                    target_status=target_status,
                )
            except ValidationError as exc:
                self.message_user(request, f"{rotation}: {exc}", level=messages.ERROR)
                continue
            changed += transition.previous_status != target_status
        if changed:
            self.message_user(request, f"Perfils actualitzats: {changed}.", level=messages.SUCCESS)

    @admin.action(description="Validar els perfils seleccionats")
    def validate_rotations(self, request, queryset):
        self._transition_selected(request, queryset, KnowledgeConcept.EditorialStatus.VALIDATED)

    @admin.action(description="Reobrir com a esborrany")
    def reopen_rotations(self, request, queryset):
        self._transition_selected(request, queryset, KnowledgeConcept.EditorialStatus.DRAFT)

    @admin.action(description="Retirar els perfils seleccionats")
    def retire_rotations(self, request, queryset):
        self._transition_selected(request, queryset, KnowledgeConcept.EditorialStatus.RETIRED)


@admin.register(ElementNotation)
class ElementNotationAdmin(admin.ModelAdmin):
    list_display = (
        "element",
        "raw_notation",
        "normalized_notation",
        "parse_status",
        "scheme",
        "updated_at",
    )
    list_filter = ("parse_status", "scheme", "direction_source", "position_source")
    search_fields = ("element__name", "raw_notation", "normalized_notation")
    autocomplete_fields = ("element", "rotation", "authored_by")
    readonly_fields = ("created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AthleteObservation)
class AthleteObservationAdmin(admin.ModelAdmin):
    list_display = (
        "athlete",
        "organization",
        "category",
        "status",
        "concept",
        "training_context",
        "authored_by",
        "observed_at",
    )
    list_filter = (
        "category",
        "status",
        "organization",
        "training_context",
        "concept__discipline",
    )
    search_fields = (
        "athlete__first_name",
        "athlete__last_name",
        "narrative",
        "evidence",
        "concept__name",
        "authored_by__first_name",
        "authored_by__last_name",
    )
    autocomplete_fields = (
        "athlete",
        "organization",
        "training_context",
        "concept",
        "authored_by",
        "supersedes",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "observed_at"
