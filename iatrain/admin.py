from django.contrib import admin

from .models import (
    AthleteObservation,
    AthleteProfile,
    CoachAthleteRelation,
    CoachProfile,
    Gym,
    GymEquipment,
    GymOrganization,
    KnowledgeConcept,
    KnowledgeRelation,
    TrainingContext,
    TrainingGroup,
    TrainingGroupMembership,
)


@admin.register(AthleteProfile)
class AthleteProfileAdmin(admin.ModelAdmin):
    list_display = ("person", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("person__first_name", "person__last_name", "person__preferred_name")
    autocomplete_fields = ("person",)
    readonly_fields = ("created_at", "updated_at")


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
    autocomplete_fields = ("target", "authored_by")
    fields = ("relation_type", "target", "editorial_status", "authored_by", "rationale")


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
    readonly_fields = ("created_at", "updated_at")
    inlines = (OutgoingKnowledgeRelationInline,)


@admin.register(KnowledgeRelation)
class KnowledgeRelationAdmin(admin.ModelAdmin):
    list_display = ("source", "relation_type", "target", "editorial_status", "authored_by", "updated_at")
    list_filter = ("editorial_status", "relation_type", "source__discipline")
    search_fields = ("source__name", "target__name", "relation_type", "rationale")
    autocomplete_fields = ("source", "target", "authored_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AthleteObservation)
class AthleteObservationAdmin(admin.ModelAdmin):
    list_display = (
        "athlete",
        "category",
        "status",
        "concept",
        "training_context",
        "authored_by",
        "observed_at",
    )
    list_filter = ("category", "status", "training_context", "concept__discipline")
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
        "training_context",
        "concept",
        "authored_by",
        "supersedes",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "observed_at"
