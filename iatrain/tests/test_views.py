from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve, reverse

from core.models import Person
from core.services import set_coach_athlete_relation
from iatrain.models import AthleteObservation, TrainingContext


class IatrainHomeTests(TestCase):
    def test_public_home_is_real_and_has_honest_empty_state(self):
        response = self.client.get(reverse("iatrain_home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(resolve("/iatrain/").url_name, "iatrain_home")
        self.assertContains(response, "IA Train")
        self.assertContains(response, "La generació d’entrenaments amb IA encara no està implementada")
        self.assertContains(response, "IA Train ja té una base funcional")
        self.assertContains(response, 'href="{}"'.format(reverse("login")))

    def test_navigation_marks_iatrain_active_and_home_links_to_it(self):
        response = self.client.get(reverse("iatrain_home"))
        platform = self.client.get(reverse("home"))

        self.assertContains(
            response,
            'class="platform-nav-item platform-nav-item--train is-active"',
        )
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(platform, 'href="{}"'.format(reverse("iatrain_home")))
        self.assertContains(platform, "MVP disponible")
        self.assertNotContains(platform, "platform-nav-item--train is-disabled")

    def test_authenticated_account_without_person_gets_identity_empty_state(self):
        user = get_user_model().objects.create_user(username="unlinked")
        self.client.force_login(user)

        response = self.client.get(reverse("iatrain_home"))

        self.assertContains(response, "El compte encara no està vinculat a una persona")
        self.assertContains(response, 'href="{}"'.format(reverse("platform_settings")))

    def test_coach_sees_only_athletes_contexts_and_observations_granted_by_relation(self):
        user = get_user_model().objects.create_user(username="coach")
        coach = Person.objects.create(user=user, first_name="Joan", last_name="Puig")
        athlete = Person.objects.create(first_name="Aina", last_name="Serra")
        hidden_athlete = Person.objects.create(first_name="Berta", last_name="Prat")
        set_coach_athlete_relation(
            coach=coach,
            athlete=athlete,
            can_view_training=True,
        )
        set_coach_athlete_relation(
            coach=coach,
            athlete=hidden_athlete,
            function="assistant",
            can_view_training=False,
        )
        context = TrainingContext.objects.create(
            name="Preparació de tardor",
            responsible_coach=coach,
            status=TrainingContext.Status.ACTIVE,
        )
        context.athletes.add(athlete)
        AthleteObservation.objects.create(
            athlete=athlete,
            training_context=context,
            narrative="Recepció més estable.",
            authored_by=coach,
        )
        AthleteObservation.objects.create(
            athlete=hidden_athlete,
            narrative="No s'ha de mostrar.",
            authored_by=coach,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("iatrain_home"))

        self.assertContains(response, "Aina Serra")
        self.assertContains(response, "Preparació de tardor")
        self.assertContains(response, "Recepció més estable")
        self.assertNotContains(response, "Berta Prat")
        self.assertNotContains(response, "No s'ha de mostrar")

