from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from iatrain.models import KnowledgeConcept, KnowledgeRelation
from iatrain.library import exercise_illustration, family_movement_badge
from iatrain.services import activate_coach_profile
from iatrain_exercises.models import Exercise, ExerciseCatalog, ExerciseRevision


class IatrainLibraryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="library-coach")
        self.person = self.user.person
        self.person.first_name = "Marta"
        self.person.last_name = "Rius"
        self.person.is_provisional = False
        self.person.save()
        activate_coach_profile(person=self.person)
        self.client.force_login(self.user)

        self.catalog = ExerciseCatalog.objects.create(
            owner=self.person,
            code="personal",
            name="Catàleg de Marta",
        )
        self.family = Exercise.objects.create(
            catalog=self.catalog,
            code="squat",
            name="Esquat",
            kind=Exercise.Kind.FAMILY,
            created_by=self.person,
        )
        variant = Exercise.objects.create(
            catalog=self.catalog,
            code="barbell_squat",
            name="Esquat amb barra",
            kind=Exercise.Kind.VARIANT,
            parent=self.family,
            created_by=self.person,
        )
        self.revision = ExerciseRevision.objects.create(
            exercise=variant,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.INTERMEDIATE,
            laterality=ExerciseRevision.Laterality.BILATERAL,
            kinetic_chain=ExerciseRevision.KineticChain.CLOSED,
            movement_pattern=ExerciseRevision.MovementPattern.SQUAT,
            description="Variant de força amb càrrega externa.",
            setup="Col·loca la barra de manera estable.",
            execution="Flexiona i estén maluc, genoll i turmell.",
            coaching_cues="Mantén el tronc estable.",
            authored_by=self.person,
        )

        self.skill = KnowledgeConcept.objects.create(
            name="Barani agrupat",
            description="Element tècnic de trampolí.",
            kind=KnowledgeConcept.Kind.SKILL,
            discipline="trampoline",
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            authored_by=self.person,
        )
        feet = KnowledgeConcept.objects.create(
            name="Peus",
            kind=KnowledgeConcept.Kind.CONTACT_POSITION,
            discipline="trampoline",
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            authored_by=self.person,
        )
        KnowledgeRelation.objects.create(
            source=self.skill,
            target=feet,
            relation_type=KnowledgeRelation.RelationType.STARTS_FROM_CONTACT,
            editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            authored_by=self.person,
        )
        self.draft_skill = KnowledgeConcept.objects.create(
            name="Element tècnic pendent",
            kind=KnowledgeConcept.Kind.SKILL,
            discipline="trampoline",
            authored_by=self.person,
        )

    def test_library_is_a_primary_coach_destination(self):
        response = self.client.get(reverse("iatrain_library"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Biblioteca d’entrenament")
        self.assertContains(response, "Esquat")
        self.assertContains(response, "Esquat amb barra")
        self.assertContains(response, "Barani agrupat")
        self.assertContains(response, 'href="/iatrain/biblioteca/"')
        self.assertEqual(response.context["library"]["result_count"], 2)

    def test_personal_search_is_owner_scoped_and_searches_variant_content(self):
        outsider = get_user_model().objects.create_user(username="other-library-owner").person
        outsider.is_provisional = False
        outsider.save()
        other_catalog = ExerciseCatalog.objects.create(
            owner=outsider,
            code="personal",
            name="Catàleg aliè",
        )
        other_family = Exercise.objects.create(
            catalog=other_catalog,
            code="lunge",
            name="Gambada aliena",
            kind=Exercise.Kind.FAMILY,
            created_by=outsider,
        )
        other_variant = Exercise.objects.create(
            catalog=other_catalog,
            code="other_lunge",
            name="Gambada aliena amb barra",
            kind=Exercise.Kind.VARIANT,
            parent=other_family,
            created_by=outsider,
        )
        ExerciseRevision.objects.create(
            exercise=other_variant,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.BEGINNER,
            laterality=ExerciseRevision.Laterality.UNILATERAL,
            kinetic_chain=ExerciseRevision.KineticChain.CLOSED,
            movement_pattern=ExerciseRevision.MovementPattern.SQUAT,
            description="Contingut que no s’ha de compartir.",
            setup="Prepara la posició.",
            execution="Executa el moviment.",
            coaching_cues="Controla el gest.",
            authored_by=outsider,
        )

        response = self.client.get(
            reverse("iatrain_library"),
            {"q": "barra", "domain": "physical"},
        )

        self.assertContains(response, "Esquat amb barra")
        self.assertNotContains(response, "Gambada aliena")
        self.assertEqual(response.context["library"]["result_count"], 1)

        response = self.client.get(
            reverse("iatrain_library"),
            {"q": "Intermedi", "domain": "physical"},
        )
        self.assertContains(response, "Esquat amb barra")

    def test_relation_names_are_searchable_but_professional_drafts_are_hidden(self):
        response = self.client.get(
            reverse("iatrain_library"),
            {"q": "Peus", "domain": "technical"},
        )

        self.assertContains(response, "Barani agrupat")
        self.assertContains(response, "Comença des de")
        self.assertNotContains(response, "Element tècnic pendent")

        hidden_target = KnowledgeConcept.objects.create(
            name="Contacte encara no publicat",
            kind=KnowledgeConcept.Kind.CONTACT_POSITION,
            discipline="trampoline",
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            authored_by=self.person,
        )
        KnowledgeRelation.objects.create(
            source=self.skill,
            target=hidden_target,
            relation_type=KnowledgeRelation.RelationType.ENDS_IN_CONTACT,
            authored_by=self.person,
        )
        response = self.client.get(
            reverse("iatrain_library"),
            {"q": "encara no publicat", "domain": "technical"},
        )
        self.assertNotContains(response, "Barani agrupat")

    def test_superuser_can_review_professional_drafts(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=("is_staff", "is_superuser"))

        response = self.client.get(
            reverse("iatrain_library"),
            {"domain": "technical", "status": "draft"},
        )

        self.assertContains(response, "Element tècnic pendent")
        self.assertNotContains(response, "Barani agrupat")

    def test_active_coach_profile_is_required(self):
        athlete_only = get_user_model().objects.create_user(username="library-athlete")
        athlete_only.person.is_provisional = False
        athlete_only.person.save()
        self.client.force_login(athlete_only)

        response = self.client.get(reverse("iatrain_library"))

        self.assertEqual(response.status_code, 403)

    def test_movement_badges_are_short_and_do_not_mislabel_push_ups(self):
        self.assertEqual(family_movement_badge("hip_abduction")["short"], "AB")
        self.assertEqual(family_movement_badge("hip_adduction")["short"], "AD")
        self.assertEqual(
            family_movement_badge("shoulder_external_rotation")["short"],
            "ROT EXT",
        )
        self.assertEqual(
            family_movement_badge("shoulder_internal_rotation")["short"],
            "ROT INT",
        )
        self.assertEqual(family_movement_badge("knee_flexion")["short"], "FLEX")
        self.assertEqual(family_movement_badge("knee_extension")["short"], "EXT")
        self.assertIsNone(family_movement_badge("push_up"))

    def test_bodyweight_squat_pilot_has_responsive_illustration(self):
        illustration = exercise_illustration("bodyweight_squat")

        self.assertTrue(illustration["large_url"].endswith("bodyweight_squat-v1-960.webp"))
        self.assertTrue(illustration["small_url"].endswith("bodyweight_squat-v1-480.webp"))
        self.assertIsNone(exercise_illustration("exercise_without_asset"))

        variant = Exercise.objects.create(
            catalog=self.catalog,
            code="bodyweight_squat",
            name="Esquat amb pes corporal",
            kind=Exercise.Kind.VARIANT,
            parent=self.family,
            created_by=self.person,
        )
        revision = ExerciseRevision.objects.create(
            exercise=variant,
            revision_number=1,
            modality=ExerciseRevision.Modality.STRENGTH,
            execution_type=ExerciseRevision.ExecutionType.DYNAMIC,
            difficulty=ExerciseRevision.Difficulty.BEGINNER,
            laterality=ExerciseRevision.Laterality.BILATERAL,
            kinetic_chain=ExerciseRevision.KineticChain.CLOSED,
            movement_pattern=ExerciseRevision.MovementPattern.SQUAT,
            description="Esquat sense càrrega externa.",
            setup="Dempeus amb els peus estables.",
            execution="Descendeix i torna dempeus.",
            coaching_cues="Mantén els talons recolzats.",
            authored_by=self.person,
        )

        response = self.client.get(
            reverse("iatrain_library"),
            {"domain": "physical", "item": f"physical:{revision.pk}"},
        )
        self.assertContains(response, "bodyweight_squat-v1-960.webp")
        self.assertContains(response, "bodyweight_squat-v1-480.webp")
        self.assertContains(response, "Descens")
