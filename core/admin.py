from django.contrib import admin

from .models import CoachAthleteRelation, Membership, Organization, Person


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("organization",)


class CoachRelationInline(admin.TabularInline):
    model = CoachAthleteRelation
    fk_name = "athlete"
    extra = 0
    autocomplete_fields = ("coach", "organization")


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
    inlines = (MembershipInline, CoachRelationInline)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "slug", "is_active", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("person", "organization", "role", "title", "is_active", "end_date")
    list_filter = ("role", "is_active", "organization")
    search_fields = ("person__first_name", "person__last_name", "organization__name", "title")
    autocomplete_fields = ("person", "organization")
    readonly_fields = ("created_at", "updated_at")


@admin.register(CoachAthleteRelation)
class CoachAthleteRelationAdmin(admin.ModelAdmin):
    list_display = (
        "coach",
        "athlete",
        "organization",
        "function",
        "is_active",
        "can_edit_training",
        "can_view_health_data",
    )
    list_filter = ("function", "is_active", "organization")
    search_fields = (
        "coach__first_name",
        "coach__last_name",
        "athlete__first_name",
        "athlete__last_name",
    )
    autocomplete_fields = ("coach", "athlete", "organization")
    readonly_fields = ("created_at", "updated_at")

