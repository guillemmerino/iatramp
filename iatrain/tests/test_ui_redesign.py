from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import resolve, reverse

from core.models import Person
from organizations.models import Membership, MembershipRole, Organization
from iatrain.engine import build_training_selection
from iatrain.models import GymEquipment
from iatrain.services import (
    activate_athlete_profile,
    activate_coach_profile,
    add_group_member,
    create_gym,
    create_training_group,
    save_gym_equipment,
    set_coach_athlete_relation,
)


class IatrainRedesignTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="redesign-coach")
        self.person = self.user.person
        self.person.first_name = "Marta"
        self.person.last_name = "Rius"
        self.person.is_provisional = False
        self.person.save()
        activate_coach_profile(person=self.person)
        activate_athlete_profile(person=self.person)
        self.organization = Organization.objects.create(name="Club Verd", slug="club-verd")
        membership = Membership.objects.create(person=self.person, organization=self.organization)
        MembershipRole.objects.create(membership=membership, role=MembershipRole.Role.COACH)
        self.client.force_login(self.user)

    def create_athlete(self, first_name, organization=None):
        person = Person.objects.create(first_name=first_name)
        profile = activate_athlete_profile(person=person)
        set_coach_athlete_relation(
            coach=self.person,
            athlete=profile,
            organization=organization,
        )
        return profile

    def test_shell_exposes_one_mode_switch_and_coach_domains(self):
        response = self.client.get(reverse("iatrain_home"))

        self.assertContains(response, 'class="iatrain-mode-switch"', count=1)
        self.assertContains(response, "Organitzacions")
        self.assertContains(response, "Gimnasos")
        self.assertContains(response, "Començar entrenament")
        self.assertContains(response, "/static/core/avatar/controls/avatar_in.png")
        self.assertNotContains(response, "Perfil de gimnasta")
        self.assertEqual(resolve("/iatrain/engine/comencar/").func.__module__, "iatrain.views.engine.start")

    def test_athlete_mode_renders_a_separate_general_dashboard(self):
        session = self.client.session
        session["iatrain_perspective"] = "athlete"
        session.save()

        response = self.client.get(reverse("iatrain_home"))

        self.assertContains(response, "El meu espai esportiu")
        self.assertNotContains(response, 'class="iatrain-coach-bar"')
        self.assertNotContains(response, "Les meves organitzacions")

    def test_coach_can_create_a_gym_and_manage_equipment(self):
        response = self.client.post(
            reverse("iatrain_gym_create"),
            {
                "name": "Pavelló Nord",
                "location": "Barcelona",
                "organizations": [self.organization.pk],
                "notes": "Zona tècnica",
            },
        )
        gym = self.organization.training_gyms.get(name="Pavelló Nord")
        self.assertRedirects(response, reverse("iatrain_gym_detail", args=(gym.pk,)))

        response = self.client.post(
            reverse("iatrain_gym_equipment_create", args=(gym.pk,)),
            {
                "name": "Trampolí principal",
                "equipment_type": GymEquipment.EquipmentType.TRAMPOLINE,
                "quantity": 2,
                "availability": GymEquipment.Availability.AVAILABLE,
                "notes": "",
            },
        )
        self.assertRedirects(response, reverse("iatrain_gym_detail", args=(gym.pk,)))
        self.assertEqual(gym.equipment.get().quantity, 2)

    def test_engine_selection_combines_group_and_independent_athletes(self):
        grouped = self.create_athlete("Aina", organization=self.organization)
        independent = self.create_athlete("Berta")
        group = create_training_group(
            user=self.user,
            organization=self.organization,
            name="Tecnificació",
        )
        add_group_member(user=self.user, training_group=group, athlete_profile=grouped)
        gym = create_gym(
            user=self.user,
            name="Pavelló Nord",
            organizations=[self.organization],
        )
        save_gym_equipment(
            user=self.user,
            gym=gym,
            name="Trampolí",
            equipment_type=GymEquipment.EquipmentType.TRAMPOLINE,
            quantity=2,
            availability=GymEquipment.Availability.AVAILABLE,
            notes="",
        )
        save_gym_equipment(
            user=self.user,
            gym=gym,
            name="Arnès en revisió",
            equipment_type=GymEquipment.EquipmentType.HARNESS,
            quantity=1,
            availability=GymEquipment.Availability.UNAVAILABLE,
            notes="",
        )

        selection = build_training_selection(
            organization=self.organization,
            training_group=group,
            gym=gym,
            additional_athletes=[independent],
        )

        self.assertEqual({profile.pk for profile in selection.athletes}, {grouped.pk, independent.pk})
        self.assertEqual([item.name for item in selection.equipment], ["Trampolí"])

    def test_engine_options_are_scoped_to_the_selected_organization(self):
        group = create_training_group(
            user=self.user,
            organization=self.organization,
            name="Base",
        )
        gym = create_gym(
            user=self.user,
            name="Pavelló Nord",
            organizations=[self.organization],
        )

        response = self.client.get(
            reverse("iatrain_engine_context_options"),
            {"organization": self.organization.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["groups"], [{"id": group.pk, "label": "Base"}])
        self.assertEqual(response.json()["gyms"], [{"id": gym.pk, "label": "Pavelló Nord"}])

    def test_engine_contract_rejects_a_group_from_another_organization(self):
        foreign = Organization.objects.create(name="Club Aliè", slug="club-alie-redesign")
        foreign_membership = Membership.objects.create(person=self.person, organization=foreign)
        MembershipRole.objects.create(
            membership=foreign_membership,
            role=MembershipRole.Role.COACH,
        )
        foreign_group = create_training_group(
            user=self.user,
            organization=foreign,
            name="Alt rendiment",
        )

        with self.assertRaises(ValidationError):
            build_training_selection(
                organization=self.organization,
                training_group=foreign_group,
            )

    def test_invalid_engine_organization_is_a_form_error_not_a_server_error(self):
        response = self.client.post(
            reverse("iatrain_training_start"),
            {"organization": "not-an-id"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["organization"])
