from django.contrib import admin

from .models import (
    Membership,
    MembershipPermission,
    MembershipRole,
    Organization,
    OrganizationMembershipRequest,
    OrganizationMembershipRequestRole,
)


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

