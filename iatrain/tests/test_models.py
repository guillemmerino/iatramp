from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import Person
from organizations.models import Organization
from iatrain.models import (
    AthleteObservation,
    AthleteProfile,
    CoachAthleteRelation,
    CoachProfile,
    KnowledgeConcept,
    KnowledgeRelation,
    TrainingContext,
    TrainingGroup,
    TrainingGroupMembership,
)


class IatrainModelTests(TestCase):
    def setUp(self):
        self.coach = Person.objects.create(first_name="Joan", last_name="Puig")
        self.athlete = Person.objects.create(first_name="Aina", last_name="Serra")
        self.other_athlete = Person.objects.create(first_name="Berta", last_name="Prat")
        self.organization = Organization.objects.create(
            name="CEO La Marbella",
            slug="ceo-la-marbella",
        )
        self.context = TrainingContext.objects.create(
            name="Temporada base",
            responsible_coach=self.coach,
            discipline="trampoline",
            status=TrainingContext.Status.ACTIVE,
        )
        self.context.athletes.add(self.athlete)

    def concept(self, name="Recepció estable", **kwargs):
        return KnowledgeConcept.objects.create(
            name=name,
            kind=kwargs.pop("kind", KnowledgeConcept.Kind.SKILL),
            discipline=kwargs.pop("discipline", "trampoline"),
            authored_by=self.coach,
            **kwargs,
        )

    def test_training_context_supports_multiple_athletes_and_validates_dates(self):
        self.context.athletes.add(self.other_athlete)
        self.assertEqual(self.context.athletes.count(), 2)

        invalid = TrainingContext(
            name="Dates invertides",
            responsible_coach=self.coach,
            valid_from=timezone.localdate(),
            valid_until=timezone.localdate() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_person_can_activate_both_training_profiles(self):
        athlete_profile = AthleteProfile.objects.create(person=self.coach)
        coach_profile = CoachProfile.objects.create(person=self.coach)

        self.assertEqual(athlete_profile.person, coach_profile.person)

    def test_athlete_profile_accepts_structured_extracted_facts(self):
        profile = AthleteProfile(
            person=self.athlete,
            extracted_facts=[
                {
                    "key": "approximate_age",
                    "value": 30,
                    "confidence": 0.8,
                    "source": "La seva edat és sobre els 30.",
                    "status": "unconfirmed",
                }
            ],
        )

        profile.full_clean()

        profile.extracted_facts[0]["confidence"] = 2
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_training_group_has_a_temporal_athlete_roster(self):
        profile = AthleteProfile.objects.create(person=self.athlete)
        group = TrainingGroup.objects.create(
            organization=self.organization,
            name="Adults",
        )
        membership = TrainingGroupMembership.objects.create(
            training_group=group,
            athlete_profile=profile,
        )

        self.assertEqual(list(group.athletes.all()), [profile])
        self.assertTrue(membership.is_current())

        with self.assertRaises(IntegrityError), transaction.atomic():
            TrainingGroupMembership.objects.create(
                training_group=group,
                athlete_profile=profile,
            )

    def test_training_group_name_is_unique_per_organization_ignoring_case(self):
        TrainingGroup.objects.create(organization=self.organization, name="Adults")

        with self.assertRaises(IntegrityError), transaction.atomic():
            TrainingGroup.objects.create(organization=self.organization, name="ADULTS")

    def test_training_group_membership_rejects_inverted_dates(self):
        profile = AthleteProfile.objects.create(person=self.athlete)
        group = TrainingGroup.objects.create(
            organization=self.organization,
            name="Adults",
        )
        membership = TrainingGroupMembership(
            training_group=group,
            athlete_profile=profile,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() - timedelta(days=1),
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_athlete_can_have_multiple_coaches(self):
        second_coach = Person.objects.create(first_name="Laia", last_name="Prat")
        athlete_profile = AthleteProfile.objects.create(person=self.athlete)
        first_profile = CoachProfile.objects.create(person=self.coach)
        second_profile = CoachProfile.objects.create(person=second_coach)
        CoachAthleteRelation.objects.create(
            coach_profile=first_profile,
            athlete_profile=athlete_profile,
        )
        CoachAthleteRelation.objects.create(
            coach_profile=second_profile,
            athlete_profile=athlete_profile,
            function=CoachAthleteRelation.Function.ASSISTANT_COACH,
        )

        self.assertEqual(athlete_profile.coach_relations.count(), 2)

    def test_relation_rejects_self_coaching_and_incoherent_permissions(self):
        coach_profile = CoachProfile.objects.create(person=self.coach)
        own_athlete_profile = AthleteProfile.objects.create(person=self.coach)
        athlete_profile = AthleteProfile.objects.create(person=self.athlete)
        self_relation = CoachAthleteRelation(
            coach_profile=coach_profile,
            athlete_profile=own_athlete_profile,
        )
        with self.assertRaises(ValidationError):
            self_relation.full_clean()

        invalid_permissions = CoachAthleteRelation(
            coach_profile=coach_profile,
            athlete_profile=athlete_profile,
            can_view_training=False,
            can_edit_training=True,
        )
        with self.assertRaises(ValidationError):
            invalid_permissions.full_clean()

    def test_global_relation_is_unique_for_function(self):
        coach_profile = CoachProfile.objects.create(person=self.coach)
        athlete_profile = AthleteProfile.objects.create(person=self.athlete)
        CoachAthleteRelation.objects.create(
            coach_profile=coach_profile,
            athlete_profile=athlete_profile,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CoachAthleteRelation.objects.create(
                coach_profile=coach_profile,
                athlete_profile=athlete_profile,
            )

    def test_concept_kind_and_attributes_are_extensible_but_duplicates_are_rejected(self):
        concept = self.concept(
            kind="biomechanical_cue",
            attributes={"plane": "sagittal", "review_needed": True},
        )
        self.assertEqual(concept.kind, "biomechanical_cue")
        self.assertEqual(concept.attributes["plane"], "sagittal")

        with self.assertRaises(ValidationError):
            self.concept(name="RECEPCIÓ ESTABLE", kind="biomechanical_cue")

    def test_knowledge_relation_is_directed_unique_and_cannot_loop(self):
        source = self.concept("Posició agrupada", kind=KnowledgeConcept.Kind.TECHNICAL_COMPONENT)
        target = self.concept("Mortal endavant", kind=KnowledgeConcept.Kind.SKILL)
        relation = KnowledgeRelation.objects.create(
            source=source,
            target=target,
            relation_type=KnowledgeRelation.RelationType.REQUIRES,
            authored_by=self.coach,
        )
        self.assertEqual(relation.source, source)

        loop = KnowledgeRelation(
            source=source,
            target=source,
            relation_type=KnowledgeRelation.RelationType.REQUIRES,
            authored_by=self.coach,
        )
        with self.assertRaises(ValidationError):
            loop.full_clean()

        with self.assertRaises(ValidationError):
            KnowledgeRelation.objects.create(
                source=source,
                target=target,
                relation_type=KnowledgeRelation.RelationType.REQUIRES,
                authored_by=self.coach,
            )

    def test_validated_relation_cannot_point_to_retired_concept(self):
        source = self.concept("Error retirat", editorial_status=KnowledgeConcept.EditorialStatus.RETIRED)
        target = self.concept("Exercici correctiu", kind=KnowledgeConcept.Kind.EXERCISE)
        relation = KnowledgeRelation(
            source=source,
            target=target,
            relation_type=KnowledgeRelation.RelationType.CORRECTS,
            editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            authored_by=self.coach,
        )
        with self.assertRaises(ValidationError):
            relation.full_clean()

    def test_free_observation_does_not_require_a_concept(self):
        observation = AthleteObservation(
            athlete=self.athlete,
            training_context=self.context,
            category=AthleteObservation.Category.NOTE,
            narrative="Avui manté millor el ritme de la sèrie.",
            authored_by=self.coach,
        )
        observation.full_clean()
        observation.save()
        self.assertIsNone(observation.concept)

    def test_observation_requires_athlete_to_belong_to_context(self):
        observation = AthleteObservation(
            athlete=self.other_athlete,
            training_context=self.context,
            narrative="No pertany al context.",
            authored_by=self.coach,
        )
        with self.assertRaises(ValidationError):
            observation.full_clean()

    def test_linked_concept_must_match_context_discipline_or_be_general(self):
        dmt_concept = self.concept("Entrada DMT", discipline="dmt")
        observation = AthleteObservation(
            athlete=self.athlete,
            training_context=self.context,
            concept=dmt_concept,
            narrative="Àmbit inconsistent.",
            authored_by=self.coach,
        )
        with self.assertRaises(ValidationError):
            observation.full_clean()

        general = self.concept("Control corporal", discipline="general")
        observation.concept = general
        observation.full_clean()

    def test_observation_bounds_and_version_athlete_are_validated(self):
        original = AthleteObservation.objects.create(
            athlete=self.athlete,
            narrative="Primera versió.",
            authored_by=self.coach,
        )
        invalid = AthleteObservation(
            athlete=self.other_athlete,
            narrative="Versió incorrecta.",
            authored_by=self.coach,
            confidence=Decimal("1.200"),
            intensity=6,
            supersedes=original,
        )
        with self.assertRaises(ValidationError) as error:
            invalid.full_clean()
        self.assertIn("confidence", error.exception.message_dict)
        self.assertIn("intensity", error.exception.message_dict)
        self.assertIn("supersedes", error.exception.message_dict)
