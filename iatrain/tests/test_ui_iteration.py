from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from core.models import Person
from organizations.models import Membership, MembershipRole, Organization
from iatrain.models import TrainingGroupMembership
from iatrain.services import (
    activate_athlete_profile,
    activate_coach_profile,
    add_group_member,
    can_manage_group,
    create_training_group,
    managed_groups,
    organizations_available_to_coach,
    remove_group_member,
    set_coach_athlete_relation,
    set_sport_profile_active,
)


class IatrainUiServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="coach-ui")
        self.person = self.user.person
        self.person.first_name = "Marta"
        self.person.last_name = "Rius"
        self.person.is_provisional = False
        self.person.save()
        self.coach_profile = activate_coach_profile(person=self.person)
        self.organization = Organization.objects.create(name="Club Blau", slug="club-blau")

    def grant_coach_role(self):
        membership = Membership.objects.create(person=self.person, organization=self.organization)
        MembershipRole.objects.create(membership=membership, role=MembershipRole.Role.COACH)
        return membership

    def test_profile_deactivation_preserves_profile_and_relations(self):
        athlete = Person.objects.create(first_name="Aina", last_name="Serra")
        relation = set_coach_athlete_relation(coach=self.person, athlete=athlete)

        profile = set_sport_profile_active(person=self.person, profile_type="coach", is_active=False)

        self.assertFalse(profile.is_active)
        self.assertTrue(type(relation).objects.filter(pk=relation.pk).exists())
        self.assertEqual(profile.pk, set_sport_profile_active(person=self.person, profile_type="coach", is_active=True).pk)

    def test_administrative_membership_does_not_authorize_group_creation(self):
        membership = Membership.objects.create(person=self.person, organization=self.organization)
        MembershipRole.objects.create(membership=membership, role=MembershipRole.Role.ADMIN)

        self.assertFalse(organizations_available_to_coach(self.user).exists())
        with self.assertRaises(PermissionDenied):
            create_training_group(user=self.user, organization=self.organization, name="Tecnificació")

    def test_explicit_coach_role_can_create_but_only_manager_can_manage_group(self):
        self.grant_coach_role()
        group = create_training_group(user=self.user, organization=self.organization, name="Tecnificació")
        outsider = get_user_model().objects.create_user(username="outsider")

        self.assertTrue(can_manage_group(self.user, group))
        self.assertIn(group, managed_groups(self.user))
        self.assertFalse(can_manage_group(outsider, group))

    def test_add_member_requires_scoped_relation_and_removal_preserves_history(self):
        self.grant_coach_role()
        group = create_training_group(user=self.user, organization=self.organization, name="Base")
        athlete = Person.objects.create(first_name="Aina", last_name="Serra")
        athlete_profile = activate_athlete_profile(person=athlete)
        set_coach_athlete_relation(coach=self.person, athlete=athlete, organization=None)

        with self.assertRaises(PermissionDenied):
            add_group_member(user=self.user, training_group=group, athlete_profile=athlete_profile)

        set_coach_athlete_relation(coach=self.person, athlete=athlete, organization=self.organization)
        roster = add_group_member(user=self.user, training_group=group, athlete_profile=athlete_profile)
        remove_group_member(user=self.user, membership=roster)
        roster.refresh_from_db()
        self.assertFalse(roster.is_active)
        self.assertIsNotNone(roster.end_date)
        self.assertTrue(TrainingGroupMembership.objects.filter(pk=roster.pk).exists())


class IatrainUiViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="coach-view")
        self.person = self.user.person
        self.person.first_name = "Marta"
        self.person.is_provisional = False
        self.person.save()
        self.coach_profile = activate_coach_profile(person=self.person)
        self.athlete_profile = activate_athlete_profile(person=self.person)
        self.organization = Organization.objects.create(name="Club Verd", slug="club-verd")
        membership = Membership.objects.create(person=self.person, organization=self.organization)
        MembershipRole.objects.create(membership=membership, role=MembershipRole.Role.COACH)
        self.client.force_login(self.user)

    def test_perspective_is_validated_and_persisted_in_session(self):
        response = self.client.post(reverse("iatrain_perspective"), {"perspective": "athlete"})
        self.assertRedirects(response, reverse("iatrain_home"))
        self.assertEqual(self.client.session["iatrain_perspective"], "athlete")

        set_sport_profile_active(person=self.person, profile_type="athlete", is_active=False)
        response = self.client.post(reverse("iatrain_perspective"), {"perspective": "athlete"})
        self.assertEqual(response.status_code, 403)

    def test_profile_post_toggles_without_deleting(self):
        response = self.client.post(
            reverse("iatrain_profile_update"), {"profile_type": "coach", "next": reverse("iatrain_home")}
        )
        self.assertRedirects(response, reverse("iatrain_home"))
        self.coach_profile.refresh_from_db()
        self.assertFalse(self.coach_profile.is_active)

    def test_athlete_mode_does_not_render_coach_empty_state(self):
        session = self.client.session
        session["iatrain_perspective"] = "athlete"
        session.save()
        response = self.client.get(reverse("iatrain_home"))
        self.assertContains(response, "El meu espai esportiu")
        self.assertNotContains(response, "Encara no tens gimnastes vinculats")

    def test_create_athlete_rejects_organization_outside_allowed_choices(self):
        forbidden = Organization.objects.create(name="Club Aliè", slug="club-alie")
        response = self.client.post(
            reverse("iatrain_athlete_create"),
            {"first_name": "Aina", "organization": forbidden.pk, "function": "primary"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["organization"])
        self.assertFalse(Person.objects.filter(first_name="Aina").exists())

    def test_group_views_enforce_explicit_manager(self):
        group = create_training_group(user=self.user, organization=self.organization, name="Base")
        outsider = get_user_model().objects.create_user(username="outsider-view")
        outsider.person.is_provisional = False
        outsider.person.save()
        activate_coach_profile(person=outsider.person)
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("iatrain_group_detail", args=(group.pk,))).status_code, 403)

    def test_main_coach_flow_creates_athlete_group_and_historical_membership(self):
        response = self.client.post(
            reverse("iatrain_athlete_create"),
            {"first_name": "Aina", "last_name": "Serra", "organization": self.organization.pk, "function": "primary"},
        )
        athlete_profile = Person.objects.get(first_name="Aina").athlete_profile
        self.assertRedirects(response, reverse("iatrain_athlete_detail", args=(athlete_profile.pk,)))
        response = self.client.post(
            reverse("iatrain_group_create"),
            {"name": "Base", "organization": self.organization.pk, "description": "Iniciació"},
        )
        group = managed_groups(self.user).get(name="Base")
        self.assertRedirects(response, reverse("iatrain_group_detail", args=(group.pk,)))
        response = self.client.post(reverse("iatrain_group_detail", args=(group.pk,)), {"athlete": athlete_profile.pk})
        roster = group.memberships.get(athlete_profile=athlete_profile, is_active=True)
        self.assertRedirects(response, reverse("iatrain_group_detail", args=(group.pk,)))
        response = self.client.post(reverse("iatrain_group_member_remove", args=(group.pk, roster.pk)))
        self.assertRedirects(response, reverse("iatrain_group_detail", args=(group.pk,)))
        roster.refresh_from_db()
        self.assertFalse(roster.is_active)
