from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from organizations.models import MembershipRole, Organization
from organizations.services import create_organization_for_user


class OrganizationPublicApiTests(TestCase):
    def test_phase_two_model_is_owned_by_organizations(self):
        self.assertEqual(Organization._meta.app_label, "organizations")
        self.assertEqual(Organization._meta.db_table, "core_organization")
        self.assertEqual(
            ContentType.objects.get_for_model(Organization).app_label,
            "organizations",
        )

    def test_core_service_import_is_a_compatibility_alias(self):
        from core.services import create_organization_for_user as legacy_service

        self.assertIs(legacy_service, create_organization_for_user)

    def test_domain_service_creates_an_owner_membership(self):
        user = get_user_model().objects.create_user(username="domain-owner")
        person = user.person
        person.is_provisional = False
        person.save(update_fields=("is_provisional", "updated_at"))

        organization = create_organization_for_user(user=user, name="Club Domini")

        self.assertTrue(
            organization.memberships.get(person=person).roles.filter(
                role=MembershipRole.Role.OWNER,
                is_active=True,
            ).exists()
        )
