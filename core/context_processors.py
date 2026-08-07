from django.utils.functional import SimpleLazyObject

from organizations.selectors import reviewable_membership_requests_for_user

from .assistant import get_assistant_context


def assistant(request):
    """Expose a neutral assistant contract without importing feature modules."""

    return {"assistant_context": get_assistant_context(request)}


def platform_notifications(request):
    """Expose navigation notifications without querying pages that hide the menu."""
    return {
        "platform_pending_review_count": SimpleLazyObject(
            lambda: reviewable_membership_requests_for_user(request.user).count()
        )
    }
