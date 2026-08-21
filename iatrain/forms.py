from django import forms

from iatrain_motion.models import MotionConcept
from organizations.models import Organization

from .models import (
    AthleteCondition,
    AthleteMeasurement,
    AthleteObservation,
    AthleteProfile,
    AthleteSportProfile,
    CoachAthleteRelation,
    GymEquipment,
)
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
    function = forms.ChoiceField(
        label="Relació amb el gimnasta",
        choices=CoachAthleteRelation.Function.choices,
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].queryset = organizations_available_to_coach(user)


class AthleteSportProfileForm(forms.Form):
    discipline = forms.ChoiceField(label="Disciplina", choices=AthleteSportProfile.Discipline.choices)
    level_code = forms.CharField(label="Nivell", max_length=80, required=False)
    training_started_on = forms.DateField(
        label="Inici de la pràctica",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    preferred_laterality = forms.ChoiceField(
        label="Lateralitat preferent",
        choices=AthleteSportProfile.Laterality.choices,
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class AthleteMeasurementForm(forms.Form):
    domain = forms.ChoiceField(label="Àrea", choices=AthleteMeasurement.Domain.choices)
    metric_code = forms.CharField(required=False, widget=forms.HiddenInput())
    metric_label = forms.CharField(label="Nom visible", max_length=180)
    value = forms.DecimalField(label="Valor", max_digits=12, decimal_places=4)
    unit = forms.CharField(label="Unitat", max_length=40)
    side = forms.ChoiceField(label="Costat", choices=AthleteMeasurement.Side.choices)
    protocol = forms.CharField(
        label="Protocol",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    source = forms.ChoiceField(label="Font", choices=AthleteMeasurement.Source.choices)
    measured_at = forms.DateTimeField(
        label="Data i hora",
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class AthleteObservationForm(forms.Form):
    category = forms.ChoiceField(label="Tipus", choices=AthleteObservation.Category.choices)
    narrative = forms.CharField(
        label="Observació",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    evidence = forms.CharField(
        label="Evidència observable",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    confidence = forms.DecimalField(
        label="Confiança",
        required=False,
        min_value=0,
        max_value=1,
        decimal_places=3,
        max_digits=4,
    )
    intensity = forms.IntegerField(
        label="Intensitat",
        required=False,
        min_value=1,
        max_value=5,
    )


class AthleteConditionForm(forms.Form):
    supersedes_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    category = forms.ChoiceField(label="Tipus", choices=AthleteCondition.Category.choices)
    title = forms.CharField(label="Títol", max_length=180)
    narrative = forms.CharField(
        label="Descripció",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    evidence = forms.CharField(
        label="Evidència",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    laterality = forms.ChoiceField(label="Costat", choices=AthleteCondition.Laterality.choices)
    severity = forms.IntegerField(
        label="Severitat",
        required=False,
        min_value=1,
        max_value=5,
    )
    training_impact = forms.ChoiceField(
        label="Impacte sobre l'entrenament",
        choices=AthleteCondition.TrainingImpact.choices,
    )
    applicability_scope = forms.ChoiceField(
        label="Abast de la condició",
        choices=AthleteCondition.ApplicabilityScope.choices,
        help_text=(
            "Indica si afecta una regió concreta, tot l’entrenament o encara cal concretar-ho."
        ),
    )
    body_region = forms.ModelChoiceField(
        label="Regió corporal",
        queryset=MotionConcept.objects.filter(
            kind__in=(
                MotionConcept.Kind.SEGMENT,
                MotionConcept.Kind.JOINT,
                MotionConcept.Kind.MUSCLE,
                MotionConcept.Kind.MUSCLE_GROUP,
            )
        ).order_by("name"),
        required=False,
        empty_label="Sense regió concreta",
    )
    source = forms.ChoiceField(label="Font", choices=AthleteCondition.Source.choices)
    valid_until = forms.DateTimeField(
        label="Vigent fins a",
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get("applicability_scope")
        region = cleaned.get("body_region")
        if scope == AthleteCondition.ApplicabilityScope.REGIONAL and not region:
            self.add_error("body_region", "Selecciona la regió corporal afectada.")
        if scope == AthleteCondition.ApplicabilityScope.GLOBAL and region:
            self.add_error(
                "body_region",
                "Deixa la regió buida quan la condició afecta globalment l’entrenament.",
            )
        if scope == AthleteCondition.ApplicabilityScope.UNKNOWN and region:
            self.add_error(
                "applicability_scope",
                "Si coneixes la regió, selecciona «Regió corporal concreta».",
            )
        return cleaned


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


class GymForm(forms.Form):
    name = forms.CharField(label="Nom del gimnàs", max_length=180)
    location = forms.CharField(label="Ubicació", max_length=240, required=False)
    organizations = forms.ModelMultipleChoiceField(
        label="Organitzacions que hi entrenen",
        queryset=Organization.objects.none(),
    )
    notes = forms.CharField(label="Observacions", widget=forms.Textarea, required=False)

    def __init__(self, *args, user, gym=None, **kwargs):
        initial = kwargs.setdefault("initial", {})
        if gym is not None and not (args and args[0]):
            initial.update(
                {
                    "name": gym.name,
                    "location": gym.location,
                    "organizations": gym.organizations.filter(gym_links__gym=gym, gym_links__is_active=True),
                    "notes": gym.notes,
                }
            )
        super().__init__(*args, **kwargs)
        self.fields["organizations"].queryset = organizations_available_to_coach(user)


class GymEquipmentForm(forms.Form):
    name = forms.CharField(label="Nom del material", max_length=180)
    equipment_type = forms.ChoiceField(label="Tipus", choices=GymEquipment.EquipmentType.choices)
    quantity = forms.IntegerField(label="Quantitat", min_value=1, initial=1)
    availability = forms.ChoiceField(label="Disponibilitat", choices=GymEquipment.Availability.choices)
    notes = forms.CharField(label="Observacions", widget=forms.Textarea, required=False)

    def __init__(self, *args, equipment=None, **kwargs):
        initial = kwargs.setdefault("initial", {})
        if equipment is not None and not (args and args[0]):
            initial.update(
                {
                    "name": equipment.name,
                    "equipment_type": equipment.equipment_type,
                    "quantity": equipment.quantity,
                    "availability": equipment.availability,
                    "notes": equipment.notes,
                }
            )
        super().__init__(*args, **kwargs)
