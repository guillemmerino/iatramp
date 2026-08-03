from django.contrib import admin

from .models import AthleteObservation, KnowledgeConcept, KnowledgeRelation, TrainingContext


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
