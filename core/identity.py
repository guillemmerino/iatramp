"""Small public helpers for the identity domain."""

from .models import Person


def person_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        person = user.person
    except Person.DoesNotExist:
        return None
    return person if person.is_active else None

