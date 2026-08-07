from django import forms

from core.models import Organization

from .models import AthleteProfile, CoachAthleteRelation
from .services import accessible_athletes, organizations_available_to_coach


class SportProfileForm(forms.Form):
    profile_type = forms.ChoiceField(choices=(("athlete", "Gimnasta"), ("coach", "Entrenador")))
    active = forms.BooleanField(required=False)


class PerspectiveForm(forms.Form):
    perspective = forms.ChoiceField(choices=(("athlete", "Gimnasta"), ("coach", "Entrenador")))

    def __init__(self, *args, person, **kwargs):
        super().__init__(*args, **kwargs)
        available = []
        for value, label, related_name in (
            ("athlete", "Gimnasta", "athlete_profile"),
            ("coach", "Entrenador", "coach_profile"),
        ):
            try:
                profile = getattr(person, related_name)
            except (AthleteProfile.DoesNotExist, AttributeError):
                continue
            if profile.is_active:
                available.append((value, label))
        self.fields["perspective"].choices = available


class UnclaimedAthleteForm(forms.Form):
    first_name = forms.CharField(label="Nom", max_length=150)
    last_name = forms.CharField(label="Cognoms", max_length=200, required=False)
    preferred_name = forms.CharField(label="Nom preferit", max_length=150, required=False)
    email = forms.EmailField(label="Correu electrònic", required=False)
    organization = forms.ModelChoiceField(
        label="Organització", queryset=Organization.objects.none(), required=False
    )
    function = forms.ChoiceField(label="Funció", choices=CoachAthleteRelation.Function.choices)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = organizations_available_to_coach(user)


class TrainingGroupForm(forms.Form):
    name = forms.CharField(label="Nom del grup", max_length=180)
    organization = forms.ModelChoiceField(label="Organització", queryset=Organization.objects.none())
    description = forms.CharField(label="Descripció", widget=forms.Textarea, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = organizations_available_to_coach(user)


class GroupMemberForm(forms.Form):
    athlete = forms.ModelChoiceField(label="Gimnasta", queryset=AthleteProfile.objects.none())

    def __init__(self, *args, user, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["athlete"].queryset = AthleteProfile.objects.filter(
            person__in=accessible_athletes(user, permission="can_view_training", organization=organization),
            is_active=True,
        ).select_related("person")
