from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import (
    CoachAthleteRelation,
    Membership,
    MembershipRole,
    Organization,
    Person,
)
from core.services import (
    can_manage_organization,
    grant_membership,
    has_athlete_access,
    link_person_to_user,
    set_coach_athlete_relation,
)


class CoreServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Club", slug="club")
        self.coach_user = get_user_model().objects.create_user(username="coach")
        self.coach = Person.objects.create(first_name="Coach", last_name="One")
        self.athlete_user = get_user_model().objects.create_user(username="athlete")
        self.athlete = Person.objects.create(
            first_name="Athlete",
            last_name="One",
            user=self.athlete_user,
        )
        link_person_to_user(person=self.coach, user=self.coach_user)

    def test_link_person_to_user_does_not_replace_an_existing_link(self):
        other_user = get_user_model().objects.create_user(username="other")
        with self.assertRaises(ValidationError):
            link_person_to_user(person=self.coach, user=other_user)

    def test_grant_membership_is_idempotent_per_role(self):
        first = grant_membership(
            person=self.coach,
            organization=self.organization,
            role=MembershipRole.Role.COACH,
            title="Tècnic",
        )
        second = grant_membership(
            person=self.coach,
            organization=self.organization,
            role=MembershipRole.Role.COACH,
            title="Tècnic principal",
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            second.roles.get(role=MembershipRole.Role.COACH).title,
            "Tècnic principal",
        )

    def test_organization_management_requires_current_admin_membership(self):
        grant_membership(
            person=self.coach,
            organization=self.organization,
            role=MembershipRole.Role.ADMIN,
        )
        self.assertTrue(can_manage_organization(self.coach_user, self.organization))

        membership = self.coach.memberships.get(organization=self.organization)
        membership.start_date = timezone.localdate() - timedelta(days=2)
        membership.end_date = timezone.localdate() - timedelta(days=1)
        membership.save()
        self.assertFalse(can_manage_organization(self.coach_user, self.organization))

    def test_explicit_relation_controls_each_access_scope(self):
        set_coach_athlete_relation(
            coach=self.coach,
            athlete=self.athlete,
            organization=self.organization,
            can_view_profile=True,
            can_view_training=True,
            can_edit_training=False,
            can_view_health_data=False,
        )

        self.assertTrue(has_athlete_access(self.coach_user, self.athlete))
        self.assertTrue(
            has_athlete_access(self.coach_user, self.athlete, "can_view_training")
        )
        self.assertFalse(
            has_athlete_access(self.coach_user, self.athlete, "can_edit_training")
        )
        self.assertFalse(
            has_athlete_access(self.coach_user, self.athlete, "can_view_health_data")
        )

    def test_inactive_or_expired_relation_does_not_grant_access(self):
        relation = set_coach_athlete_relation(coach=self.coach, athlete=self.athlete)
        relation.is_active = False
        relation.save()
        self.assertFalse(has_athlete_access(self.coach_user, self.athlete))

        relation.is_active = True
        relation.start_date = timezone.localdate() - timedelta(days=2)
        relation.end_date = timezone.localdate() - timedelta(days=1)
        relation.save()
        self.assertFalse(has_athlete_access(self.coach_user, self.athlete))

    def test_self_superuser_and_anonymous_access(self):
        self.assertTrue(has_athlete_access(self.athlete_user, self.athlete))
        self.assertFalse(has_athlete_access(AnonymousUser(), self.athlete))
        superuser = get_user_model().objects.create_superuser(
            username="root",
            email="root@example.com",
            password="test",
        )
        self.assertTrue(has_athlete_access(superuser, self.athlete, "can_view_health_data"))

    def test_unknown_permission_is_rejected(self):
        with self.assertRaises(ValueError):
            has_athlete_access(self.coach_user, self.athlete, "delete_athlete")
