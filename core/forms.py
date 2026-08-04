from django import forms

from .models import MembershipPermission, MembershipRole, Organization, Person
from .services import REQUESTABLE_ORGANIZATION_ROLES, effective_membership_permissions


class PlatformFormMixin:
    def _decorate_fields(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                continue
            widget.attrs.setdefault("class", "platform-form-control")


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


class OrganizationCreateForm(PlatformFormMixin, forms.Form):
    name = forms.CharField(max_length=255, label="Nom de l'organització")
    kind = forms.ChoiceField(choices=Organization.Kind.choices, label="Tipus")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._decorate_fields()


class OrganizationEditForm(PlatformFormMixin, forms.ModelForm):
    class Meta:
        model = Organization
        fields = ("name", "kind")
        labels = {"name": "Nom de l'organització", "kind": "Tipus"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._decorate_fields()

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        duplicate = Organization.objects.filter(name__iexact=name, is_active=True).exclude(
            pk=self.instance.pk
        )
        if duplicate.exists():
            raise forms.ValidationError("Ja existeix una organització activa amb aquest nom.")
        return name


class OrganizationJoinRequestForm(PlatformFormMixin, forms.Form):
    roles = forms.MultipleChoiceField(
        choices=[
            choice
            for choice in MembershipRole.Role.choices
            if choice[0] in REQUESTABLE_ORGANIZATION_ROLES
        ],
        widget=forms.CheckboxSelectMultiple,
        label="Rols que vols desenvolupar",
        initial=(MembershipRole.Role.MEMBER,),
    )
    message = forms.CharField(
        required=False,
        label="Missatge per als administradors",
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._decorate_fields()


class MembershipAccessForm(PlatformFormMixin, forms.Form):
    roles = forms.MultipleChoiceField(
        choices=MembershipRole.Role.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Rols",
    )
    permissions = forms.MultipleChoiceField(
        choices=MembershipPermission.Permission.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Permisos efectius",
        help_text="Els rols aporten permisos per defecte; aquesta selecció permet ajustar-los per membre.",
    )

    def __init__(self, *args, membership=None, **kwargs):
        if membership is None:
            raise TypeError("MembershipAccessForm requereix membership.")
        self.membership = membership
        if not args and "initial" not in kwargs:
            kwargs["initial"] = {
                "roles": list(
                    membership.roles.filter(is_active=True).values_list("role", flat=True)
                ),
                "permissions": list(effective_membership_permissions(membership)),
            }
        super().__init__(*args, **kwargs)
        self._decorate_fields()

    def clean_roles(self):
        roles = self.cleaned_data["roles"]
        return roles or [MembershipRole.Role.MEMBER]
