from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class OrganizationOwnershipMigrationTests(TransactionTestCase):
    migrate_from = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0005_alter_person_last_name"),
        ("iatrain", "0005_gym_gymorganization_gymequipment_gym_organizations_and_more"),
    ]
    migrate_to = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("core", "0007_release_organization_models"),
        ("iatrain", "0006_retarget_organization_relations"),
        ("organizations", "0002_move_content_types"),
    ]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Person = old_apps.get_model("core", "Person")
        Organization = old_apps.get_model("core", "Organization")
        Membership = old_apps.get_model("core", "Membership")
        MembershipRole = old_apps.get_model("core", "MembershipRole")
        TrainingGroup = old_apps.get_model("iatrain", "TrainingGroup")
        ContentType = old_apps.get_model("contenttypes", "ContentType")

        suffix = uuid4().hex
        person = Person.objects.create(first_name="Migració", last_name=suffix)
        organization = Organization.objects.create(
            name=f"Club {suffix}",
            slug=f"club-{suffix}",
            created_by_id=person.pk,
        )
        membership = Membership.objects.create(
            person_id=person.pk,
            organization_id=organization.pk,
        )
        role = MembershipRole.objects.create(
            membership_id=membership.pk,
            role="owner",
            granted_by_id=person.pk,
        )
        group = TrainingGroup.objects.create(
            organization_id=organization.pk,
            name="Grup migrat",
        )
        self.ids = {
            "organization": organization.pk,
            "membership": membership.pk,
            "role": role.pk,
            "group": group.pk,
            "content_type": ContentType.objects.get(
                app_label="core",
                model="organization",
            ).pk,
        }

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_rows_and_relations_are_adopted_without_new_ids(self):
        Organization = self.apps.get_model("organizations", "Organization")
        Membership = self.apps.get_model("organizations", "Membership")
        MembershipRole = self.apps.get_model("organizations", "MembershipRole")
        TrainingGroup = self.apps.get_model("iatrain", "TrainingGroup")

        organization = Organization.objects.get(pk=self.ids["organization"])
        membership = Membership.objects.get(pk=self.ids["membership"])
        role = MembershipRole.objects.get(pk=self.ids["role"])
        group = TrainingGroup.objects.get(pk=self.ids["group"])

        self.assertEqual(organization._meta.db_table, "core_organization")
        self.assertEqual(membership.organization_id, organization.pk)
        self.assertEqual(role.membership_id, membership.pk)
        self.assertEqual(group.organization_id, organization.pk)

    def test_content_type_keeps_its_identity_and_moves_app_label(self):
        ContentType = self.apps.get_model("contenttypes", "ContentType")

        content_type = ContentType.objects.get(
            app_label="organizations",
            model="organization",
        )
        self.assertEqual(content_type.pk, self.ids["content_type"])
        self.assertFalse(
            ContentType.objects.filter(
                app_label="core",
                model="organization",
            ).exists()
        )
