from django import forms

from organizations.models import Organization

from iatrain.models import AthleteProfile, Gym, TrainingGroup
from iatrain.services import (
    accessible_athletes,
    accessible_gyms,
    managed_groups,
    organizations_available_to_coach,
)


class TrainingStartForm(forms.Form):
    organization = forms.ModelChoiceField(
        label="Organització",
        queryset=Organization.objects.none(),
        empty_label="Selecciona una organització",
    )
    training_group = forms.ModelChoiceField(
        label="Grup",
        queryset=TrainingGroup.objects.none(),
        required=False,
        empty_label="Sense grup predefinit",
    )
    additional_athletes = forms.ModelMultipleChoiceField(
        label="Gimnastes addicionals o independents",
        queryset=AthleteProfile.objects.none(),
        required=False,
        help_text="S’afegiran als membres actius del grup sense modificar-lo.",
    )
    gym = forms.ModelChoiceField(
        label="Gimnàs",
        queryset=Gym.objects.none(),
        required=False,
        empty_label="Sense gimnàs assignat",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        organizations = organizations_available_to_coach(user)
        groups = managed_groups(user).filter(is_active=True)
        gyms = accessible_gyms(user)
        self.fields["organization"].queryset = organizations
        self.fields["additional_athletes"].queryset = AthleteProfile.objects.filter(
            person__in=accessible_athletes(user, permission="can_view_training"),
            is_active=True,
        ).select_related("person")

        organization_id = self.data.get("organization") if self.is_bound else None
        try:
            organization_id = int(organization_id)
        except (TypeError, ValueError):
            organization_id = None
        if organization_id:
            groups = groups.filter(organization_id=organization_id)
            gyms = gyms.filter(
                organization_links__organization_id=organization_id,
                organization_links__is_active=True,
            )
        else:
            groups = groups.none()
            gyms = gyms.none()
        self.fields["training_group"].queryset = groups.select_related("organization").distinct()
        self.fields["gym"].queryset = gyms.distinct()

    def clean(self):
        cleaned = super().clean()
        organization = cleaned.get("organization")
        group = cleaned.get("training_group")
        gym = cleaned.get("gym")
        if organization and group and group.organization_id != organization.pk:
            self.add_error("training_group", "El grup no pertany a l’organització seleccionada.")
        if organization and gym and not gym.organization_links.filter(
            organization=organization,
            is_active=True,
        ).exists():
            self.add_error("gym", "El gimnàs no està vinculat a l’organització seleccionada.")
        return cleaned
