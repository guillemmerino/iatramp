from django import forms

from organizations.forms import (
    MembershipAccessForm,
    OrganizationCreateForm,
    OrganizationEditForm,
    OrganizationJoinRequestForm,
)

from .form_mixins import PlatformFormMixin
from .models import Person


class PersonProfileForm(PlatformFormMixin, forms.ModelForm):
    class Meta:
        model = Person
        fields = (
            "first_name",
            "last_name",
            "preferred_name",
            "birth_date",
            "email",
            "phone",
        )
        labels = {
            "first_name": "Nom",
            "last_name": "Cognoms",
            "preferred_name": "Nom preferit",
            "birth_date": "Data de naixement",
            "email": "Correu electrònic",
            "phone": "Telèfon",
        }
        widgets = {"birth_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._decorate_fields()


# Compatibility exports for callers that have not yet adopted the new domain
# package. Organization forms are implemented in ``organizations.forms``.
__all__ = (
    "MembershipAccessForm",
    "OrganizationCreateForm",
    "OrganizationEditForm",
    "OrganizationJoinRequestForm",
    "PersonProfileForm",
)
