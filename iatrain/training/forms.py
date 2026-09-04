from django import forms

from core.models import Person

from iatrain.models import (
    PhysicalExercisePrescription,
    SessionGoal,
    SessionItemAthleteAdjustment,
    TrainingBlock,
    TrainingSessionItem,
)
from iatrain.services import accessible_athletes
from iatrain_exercises.models import ExerciseRevision
from iatrain_motion.models import EditorialStatus


class ExerciseRevisionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, revision):
        status = "" if revision.editorial_status == EditorialStatus.VALIDATED else " · esborrany"
        return f"{revision.exercise.name}{status}"


class SessionParticipantForm(forms.Form):
    athlete_profile = forms.ModelChoiceField(
        label="Gimnasta", queryset=Person.objects.none(), empty_label="Selecciona un gimnasta"
    )

    def __init__(self, *args, user, organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["athlete_profile"].queryset = (
            accessible_athletes(
                user, permission="can_edit_training", organization=organization
            )
            .filter(athlete_profile__is_active=True)
            .select_related("athlete_profile")
        )

    def clean_athlete_profile(self):
        return self.cleaned_data["athlete_profile"].athlete_profile


class SessionGoalForm(forms.Form):
    domain = forms.ChoiceField(label="Àmbit", choices=SessionGoal.Domain.choices)
    description = forms.CharField(
        label="Objectiu", widget=forms.Textarea(attrs={"rows": 2})
    )
    priority = forms.ChoiceField(label="Prioritat", choices=SessionGoal.Priority.choices)
    rationale = forms.CharField(
        label="Motiu", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )


class TrainingBlockForm(forms.Form):
    sequence_index = forms.IntegerField(label="Posició", min_value=1)
    name = forms.CharField(label="Nom del bloc", max_length=160)
    block_role = forms.ChoiceField(label="Funció", choices=TrainingBlock.Role.choices)
    domain = forms.ChoiceField(label="Àmbit", choices=TrainingBlock.Domain.choices)
    execution_mode = forms.ChoiceField(
        label="Organització", choices=TrainingBlock.ExecutionMode.choices
    )
    planned_duration_minutes = forms.IntegerField(label="Durada (min)", min_value=1)
    objective = forms.CharField(
        label="Objectiu", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    instructions = forms.CharField(
        label="Indicacions", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    rounds = forms.IntegerField(label="Rondes", min_value=1, initial=1)
    rest_between_rounds_seconds = forms.IntegerField(
        label="Descans entre rondes (s)", min_value=0, initial=0
    )
    is_optional = forms.BooleanField(label="Bloc opcional", required=False)


class TrainingItemForm(forms.Form):
    sequence_index = forms.IntegerField(label="Posició", min_value=1)
    item_type = forms.ChoiceField(label="Tipus", choices=TrainingSessionItem.ItemType.choices)
    title = forms.CharField(label="Nom", max_length=180)
    instructions = forms.CharField(
        label="Execució", required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    coaching_cues = forms.CharField(
        label="Consignes", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    setup_seconds = forms.IntegerField(
        label="Preparació (s)", min_value=0, initial=0, required=False
    )
    planned_duration_seconds = forms.IntegerField(
        label="Durada (s)", required=False, min_value=1
    )
    rest_after_seconds = forms.IntegerField(
        label="Descans posterior (s)", min_value=0, initial=0
    )
    selection_rationale = forms.CharField(
        label="Motiu de selecció",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    is_optional = forms.BooleanField(label="Ítem opcional", required=False)
    exercise_revision = ExerciseRevisionChoiceField(
        label="Exercici",
        queryset=ExerciseRevision.objects.none(),
        required=False,
        empty_label="Selecciona un exercici",
    )
    dose_mode = forms.ChoiceField(
        label="Dosi",
        choices=(
            (
                PhysicalExercisePrescription.DoseMode.REPETITIONS,
                "Repeticions",
            ),
            (PhysicalExercisePrescription.DoseMode.DURATION, "Durada"),
            (PhysicalExercisePrescription.DoseMode.HOLD, "Manteniment"),
        ),
        required=False,
    )
    sets = forms.IntegerField(label="Sèries", min_value=1, required=False, initial=1)
    repetitions = forms.IntegerField(label="Repeticions", min_value=1, required=False)
    duration_seconds = forms.IntegerField(
        label="Temps de treball (s)", min_value=1, required=False
    )
    intensity_metric = forms.ChoiceField(
        label="Intensitat",
        choices=PhysicalExercisePrescription.IntensityMetric.choices,
        required=False,
    )
    intensity_value = forms.DecimalField(
        label="Valor d'intensitat", min_value=0, required=False
    )
    rest_between_sets_seconds = forms.IntegerField(
        label="Descans entre sèries (s)", min_value=0, required=False, initial=0
    )

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["exercise_revision"].queryset = (
            ExerciseRevision.objects.filter(
                exercise__catalog__owner=owner,
            )
            .exclude(editorial_status=EditorialStatus.RETIRED)
            .select_related("exercise")
            .order_by("exercise__name", "-revision_number")
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("item_type") == TrainingSessionItem.ItemType.PHYSICAL_EXERCISE:
            if not cleaned.get("exercise_revision"):
                self.add_error("exercise_revision", "Selecciona l'exercici.")
            if not cleaned.get("dose_mode"):
                self.add_error("dose_mode", "Selecciona la dosi.")
            dose_mode = cleaned.get("dose_mode")
            if dose_mode == PhysicalExercisePrescription.DoseMode.REPETITIONS:
                if not cleaned.get("repetitions"):
                    self.add_error("repetitions", "Indica les repeticions.")
            if dose_mode in {
                PhysicalExercisePrescription.DoseMode.DURATION,
                PhysicalExercisePrescription.DoseMode.HOLD,
            } and not cleaned.get("duration_seconds"):
                self.add_error("duration_seconds", "Indica el temps de treball.")
        return cleaned


class SessionItemAthleteAdjustmentForm(forms.ModelForm):
    replacement_exercise_revision = ExerciseRevisionChoiceField(
        label="Exercici de substitució",
        queryset=ExerciseRevision.objects.none(),
        required=False,
        empty_label="Mantén l’exercici compartit",
    )

    class Meta:
        model = SessionItemAthleteAdjustment
        fields = (
            "action",
            "replacement_exercise_revision",
            "sets",
            "repetitions",
            "duration_seconds",
            "load_value",
            "load_unit",
            "intensity_metric",
            "intensity_value",
            "rest_between_sets_seconds",
            "station_remainder_action",
            "adaptation_notes",
            "rationale",
        )
        labels = {
            "action": "Decisió",
            "sets": "Sèries",
            "repetitions": "Repeticions",
            "duration_seconds": "Temps de treball individual (s)",
            "load_value": "Càrrega",
            "load_unit": "Unitat de càrrega",
            "intensity_metric": "Mètrica d’intensitat",
            "intensity_value": "Valor d’intensitat",
            "rest_between_sets_seconds": "Descans entre sèries (s)",
            "station_remainder_action": "Ús del temps restant de l’estació",
            "adaptation_notes": "Indicacions d’adaptació",
            "rationale": "Justificació",
        }
        widgets = {
            "adaptation_notes": forms.Textarea(attrs={"rows": 3}),
            "rationale": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["replacement_exercise_revision"].queryset = (
            ExerciseRevision.objects.filter(exercise__catalog__owner=owner)
            .exclude(editorial_status=EditorialStatus.RETIRED)
            .select_related("exercise")
            .order_by("exercise__name", "-revision_number")
        )

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        replacement = cleaned.get("replacement_exercise_revision")
        if action == SessionItemAthleteAdjustment.Action.SKIP:
            for field in (
                "replacement_exercise_revision",
                "sets",
                "repetitions",
                "duration_seconds",
                "load_value",
                "intensity_value",
                "rest_between_sets_seconds",
            ):
                cleaned[field] = None
            cleaned["load_unit"] = ""
            cleaned["intensity_metric"] = ""
            cleaned["station_remainder_action"] = ""
            replacement = None
        if action == SessionItemAthleteAdjustment.Action.REPLACE and not replacement:
            self.add_error(
                "replacement_exercise_revision",
                "Selecciona l’exercici de substitució.",
            )
        item = self.instance.session_item
        base_duration = None
        if item_id := getattr(item, "pk", None):
            try:
                base_duration = item.physical_prescription.duration_seconds
            except PhysicalExercisePrescription.DoesNotExist:
                base_duration = None
        duration = cleaned.get("duration_seconds")
        remainder = cleaned.get("station_remainder_action")
        circuit_modes = {
            TrainingBlock.ExecutionMode.CIRCUIT,
            TrainingBlock.ExecutionMode.STATIONS,
            TrainingBlock.ExecutionMode.PARALLEL,
            TrainingBlock.ExecutionMode.SUPERSET,
        }
        if item_id and base_duration and item.block.execution_mode in circuit_modes:
            if duration and duration > base_duration:
                self.add_error(
                    "duration_seconds",
                    "El temps individual no pot superar la durada compartida de l’estació.",
                )
            if duration and duration < base_duration and not remainder:
                self.add_error(
                    "station_remainder_action",
                    "Indica què farà la participant durant el temps restant.",
                )
        return cleaned
