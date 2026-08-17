from django.contrib import admin

from organizations.models import Membership

from .models import Person, PersonClaimInvitation, PersonMergeRecord


class MembershipInline(admin.TabularInline):
    """Cross-domain read/write convenience on the identity admin."""

    model = Membership
    fk_name = "person"
    extra = 0
    autocomplete_fields = ("organization",)
    fields = ("organization", "status", "start_date", "end_date")


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
