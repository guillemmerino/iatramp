from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .editorial import (
    transition_motion_concept,
    transition_motion_relation,
    transition_skeleton_schema,
)
from .models import (
    CanonicalJoint,
    CanonicalLandmark,
    CanonicalSegment,
    EditorialStatus,
    JointAngleDefinition,
    MotionConcept,
    MotionRelation,
    SkeletonSchema,
)


class OutgoingMotionRelationInline(admin.TabularInline):
    model = MotionRelation
    fk_name = "source"
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("relation_type", "target", "editorial_status", "rationale")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


class EditorialActionsMixin:
    actions = ("validate_selected", "reopen_selected", "retire_selected")
    transition_service = None

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

    @admin.action(description="Reobrir la selecció com a esborrany")
    def reopen_selected(self, request, queryset):
        self._transition_selected(request, queryset, EditorialStatus.DRAFT)

    @admin.action(description="Retirar la selecció")
    def retire_selected(self, request, queryset):
        self._transition_selected(request, queryset, EditorialStatus.RETIRED)


@admin.register(MotionConcept)
class MotionConceptAdmin(EditorialActionsMixin, admin.ModelAdmin):
    transition_service = staticmethod(transition_motion_concept)
    transition_argument = "concept"
    list_display = ("code", "name", "kind", "laterality", "editorial_status", "updated_at")
    list_filter = ("editorial_status", "kind", "laterality")
    search_fields = ("code", "name", "definition")
    autocomplete_fields = ("authored_by",)
    readonly_fields = ("editorial_status", "last_validated_by", "last_validated_at", "created_at", "updated_at")
    inlines = (OutgoingMotionRelationInline,)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.editorial_status != EditorialStatus.DRAFT:
            fields.extend(("code", "name", "definition", "kind", "laterality", "authored_by", "provenance"))
        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MotionRelation)
class MotionRelationAdmin(EditorialActionsMixin, admin.ModelAdmin):
    transition_service = staticmethod(transition_motion_relation)
    transition_argument = "relation"
    list_display = ("source", "relation_type", "target", "editorial_status", "updated_at")
    list_filter = ("editorial_status", "relation_type", "source__kind")
    search_fields = ("source__name", "target__name", "rationale")
    autocomplete_fields = ("source", "target", "authored_by")
    readonly_fields = ("editorial_status", "last_validated_by", "last_validated_at", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.editorial_status != EditorialStatus.DRAFT:
            fields.extend(("source", "target", "relation_type", "rationale", "authored_by", "provenance"))
        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        return False


class SkeletonDefinitionAdmin(admin.ModelAdmin):
    autocomplete_fields = ("schema", "authored_by")
    readonly_fields = ("created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.schema.editorial_status != EditorialStatus.DRAFT:
            fields.extend(
                field.name
                for field in obj._meta.fields
                if field.name not in {"id", "created_at", "updated_at"}
            )
        return tuple(dict.fromkeys(fields))

    def has_add_permission(self, request):
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SkeletonSchema)
class SkeletonSchemaAdmin(EditorialActionsMixin, admin.ModelAdmin):
    transition_service = staticmethod(transition_skeleton_schema)
    transition_argument = "schema"
    list_display = (
        "code", "version", "name", "spatial_dimensions", "editorial_status",
        "landmark_count", "segment_count", "joint_count", "updated_at",
    )
    list_filter = ("editorial_status", "spatial_dimensions")
    search_fields = ("code", "version", "name", "description")
    autocomplete_fields = ("authored_by",)
    readonly_fields = (
        "editorial_status", "last_validated_by", "last_validated_at", "created_at", "updated_at",
    )

    @admin.display(description="Punts")
    def landmark_count(self, obj):
        return obj.landmarks.count()

    @admin.display(description="Segments")
    def segment_count(self, obj):
        return obj.segments.count()

    @admin.display(description="Articulacions")
    def joint_count(self, obj):
        return obj.joints.count()

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.editorial_status != EditorialStatus.DRAFT:
            fields.extend(
                (
                    "code", "version", "name", "description", "spatial_dimensions",
                    "length_unit", "angle_unit", "coordinate_convention", "neutral_pose",
                    "authored_by", "provenance",
                )
            )
        return tuple(dict.fromkeys(fields))

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CanonicalLandmark)
class CanonicalLandmarkAdmin(SkeletonDefinitionAdmin):
    list_display = ("code", "name", "schema", "side", "landmark_type", "measurement_source")
    list_filter = ("schema", "side", "landmark_type", "measurement_source")
    search_fields = ("code", "name", "definition", "schema__name")


@admin.register(CanonicalSegment)
class CanonicalSegmentAdmin(SkeletonDefinitionAdmin):
    list_display = ("code", "concept", "side", "schema", "primary_axis", "orientation_capability")
    list_filter = ("schema", "side", "primary_axis", "orientation_capability")
    search_fields = ("code", "concept__name", "schema__name")
    autocomplete_fields = (
        "schema", "concept", "axis_start_landmark", "axis_end_landmark", "plane_landmark", "authored_by",
    )


@admin.register(CanonicalJoint)
class CanonicalJointAdmin(SkeletonDefinitionAdmin):
    list_display = ("code", "concept", "side", "schema", "proximal_segment", "distal_segment")
    list_filter = ("schema", "side")
    search_fields = ("code", "concept__name", "schema__name")
    autocomplete_fields = (
        "schema", "concept", "center_landmark", "proximal_segment", "distal_segment", "authored_by",
    )


@admin.register(JointAngleDefinition)
class JointAngleDefinitionAdmin(SkeletonDefinitionAdmin):
    list_display = ("code", "joint", "component", "calculation_method", "schema")
    list_filter = ("schema", "component", "calculation_method")
    search_fields = ("code", "joint__code", "positive_action__name", "negative_action__name")
    autocomplete_fields = (
        "schema", "joint", "positive_action", "negative_action", "plane", "axis", "authored_by",
    )
