from django.contrib import admin

from .models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
    OrganizationMembershipRequestRole,
    Person,
    PersonClaimInvitation,
    PersonMergeRecord,
)


class MembershipInline(admin.TabularInline):
    model = Membership
    fk_name = "person"
    extra = 0
    autocomplete_fields = ("organization",)
    fields = ("organization", "status", "start_date", "end_date")


class MembershipRoleInline(admin.TabularInline):
    model = MembershipRole
    extra = 0
    autocomplete_fields = ("granted_by",)


class MembershipPermissionInline(admin.TabularInline):
    model = MembershipPermission
    extra = 0
    autocomplete_fields = ("granted_by",)


class MembershipRequestRoleInline(admin.TabularInline):
    model = OrganizationMembershipRequestRole
    extra = 0


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("display_name", "email", "user", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = (
        "first_name",
        "last_name",
        "preferred_name",
        "email",
        "user__username",
        "user__email",
    )
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (MembershipInline,)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "slug", "created_by", "is_active", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("created_by",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("person", "organization", "status", "roles_summary", "end_date")
    list_filter = ("status", "roles__role", "organization")
    search_fields = ("person__first_name", "person__last_name", "organization__name")
    autocomplete_fields = ("person", "organization", "approved_by")
    readonly_fields = ("created_at", "updated_at")
    inlines = (MembershipRoleInline, MembershipPermissionInline)

    @admin.display(description="Rols")
    def roles_summary(self, obj):
        return obj.role_summary


@admin.register(OrganizationMembershipRequest)
class OrganizationMembershipRequestAdmin(admin.ModelAdmin):
    list_display = ("person", "organization", "status", "roles_summary", "created_at")
    list_filter = ("status", "organization", "requested_roles__role")
    search_fields = ("person__first_name", "person__last_name", "organization__name")
    autocomplete_fields = ("person", "organization", "resolved_by")
    readonly_fields = ("created_at", "updated_at", "resolved_at")
    inlines = (MembershipRequestRoleInline,)

    @admin.display(description="Rols demanats")
    def roles_summary(self, obj):
        return obj.requested_role_summary



@admin.register(PersonClaimInvitation)
class PersonClaimInvitationAdmin(admin.ModelAdmin):
    list_display = ("person", "email", "status", "created_by", "expires_at")
    list_filter = ("status",)
    search_fields = ("person__first_name", "person__last_name", "email")
    autocomplete_fields = ("person", "created_by", "claimed_by")
    readonly_fields = ("token_digest", "claimed_at", "created_at", "updated_at")


@admin.register(PersonMergeRecord)
class PersonMergeRecordAdmin(admin.ModelAdmin):
    list_display = ("duplicate_person_id", "canonical_person", "merged_by", "created_at")
    search_fields = (
        "canonical_person__first_name",
        "canonical_person__last_name",
        "duplicate_person_id",
    )
    autocomplete_fields = ("canonical_person", "merged_by")
    readonly_fields = (
        "canonical_person",
        "duplicate_person_id",
        "duplicate_snapshot",
        "merged_by",
        "created_at",
    )
