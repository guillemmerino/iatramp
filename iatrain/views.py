from django.db.models import Q
from django.views.generic import TemplateView

from .models import AthleteObservation, TrainingContext
from .services import accessible_athletes, person_for_user


class IatrainHomeView(TemplateView):
    template_name = "iatrain/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = person_for_user(self.request.user)
        athletes = accessible_athletes(self.request.user)
        athlete_ids = list(athletes.values_list("pk", flat=True))

        training_contexts = TrainingContext.objects.none()
        observations = AthleteObservation.objects.none()
        if person is not None:
            training_contexts = (
                TrainingContext.objects.filter(
                    Q(responsible_coach=person) | Q(athletes__in=athlete_ids)
                )
                .select_related("organization", "responsible_coach")
                .prefetch_related("athletes")
                .distinct()[:12]
            )
            observations = (
                AthleteObservation.objects.filter(athlete_id__in=athlete_ids)
                .select_related("athlete", "training_context", "concept", "authored_by")[:20]
            )

        context.update(
            {
                "iatrain_person": person,
                "iatrain_athletes": list(athletes.order_by("last_name", "first_name")),
                "iatrain_contexts": list(training_contexts),
                "iatrain_observations": list(observations),
            }
        )
        return context

