from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class IdentityAndTrainingProfilesMigrationTests(TransactionTestCase):
    migrate_from = [("core", "0002_organization_membership_workflows"), ("iatrain", "0001_initial")]
    migrate_to = [
        ("iatrain", "0002_athleteprofile_coachprofile_coachathleterelation_and_more"),
        ("core", "0004_remove_legacy_coachathleterelation"),
    ]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        User = old_apps.get_model("auth", "User")
        Person = old_apps.get_model("core", "Person")
        LegacyRelation = old_apps.get_model("core", "CoachAthleteRelation")

        suffix = uuid4().hex
        linked_user = User.objects.create(username=f"migration-coach-{suffix}")
        unlinked_user = User.objects.create(username=f"migration-new-user-{suffix}")
        coach = Person.objects.create(
            user_id=linked_user.pk,
            first_name="Joan",
            last_name="Puig",
        )
        athlete = Person.objects.create(first_name="Aina", last_name="Serra")
        legacy = LegacyRelation.objects.create(
            coach_id=coach.pk,
            athlete_id=athlete.pk,
            can_edit_training=True,
            notes="Relació anterior",
        )
        self.ids = {
            "coach": coach.pk,
            "athlete": athlete.pk,
            "legacy": legacy.pk,
            "unlinked_user": unlinked_user.pk,
        }

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_relations_move_to_profiles_and_users_get_people(self):
        Person = self.apps.get_model("core", "Person")
        AthleteProfile = self.apps.get_model("iatrain", "AthleteProfile")
        CoachProfile = self.apps.get_model("iatrain", "CoachProfile")
        Relation = self.apps.get_model("iatrain", "CoachAthleteRelation")

        coach_profile = CoachProfile.objects.get(person_id=self.ids["coach"])
        athlete_profile = AthleteProfile.objects.get(person_id=self.ids["athlete"])
        relation = Relation.objects.get(
            coach_profile_id=coach_profile.pk,
            athlete_profile_id=athlete_profile.pk,
        )
        provisional = Person.objects.get(user_id=self.ids["unlinked_user"])

        self.assertTrue(relation.can_edit_training)
        self.assertEqual(relation.notes, "Relació anterior")
        self.assertTrue(provisional.is_provisional)
from uuid import uuid4
