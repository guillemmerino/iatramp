from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from iatrain.editorial import (
    transition_element_rotation,
    transition_knowledge_concept,
    transition_knowledge_relation,
)
from iatrain.models import (
    ElementRotation,
    ElementRotationSegment,
    KnowledgeConcept,
    KnowledgeEditorialEvent,
    KnowledgeRelation,
)
from iatrain.services import create_knowledge_concept, create_knowledge_relation


class EditorialGovernanceTests(TestCase):
    def setUp(self):
        self.reviewer_user = get_user_model().objects.create_superuser(
            username="editorial-reviewer",
            password="unused",
        )
        self.regular_user = get_user_model().objects.create_user(
            username="editorial-author",
            password="unused",
        )
        self.reviewer = self.reviewer_user.person
        self.author = self.regular_user.person

    def concept(self, name, kind=KnowledgeConcept.Kind.SKILL):
        return create_knowledge_concept(
            author=self.author,
            name=name,
            kind=kind,
        )

    def test_new_knowledge_always_enters_as_draft(self):
        with self.assertRaises(ValidationError):
            create_knowledge_concept(
                author=self.author,
                name="Entrada validada indeguda",
                kind=KnowledgeConcept.Kind.SKILL,
                editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            )

        source = self.concept("Origen")
        target = self.concept("Destí")
        with self.assertRaises(ValidationError):
            create_knowledge_relation(
                author=self.author,
                source=source,
                target=target,
                relation_type=KnowledgeRelation.RelationType.REQUIRES,
                editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            )

    def test_only_superusers_can_make_editorial_transitions(self):
        concept = self.concept("Accés editorial")

        with self.assertRaises(PermissionDenied):
            transition_knowledge_concept(
                user=self.regular_user,
                concept=concept,
                target_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            )

    def test_relation_validation_requires_validated_endpoints_and_is_audited(self):
        source = self.concept("Progressió inicial")
        target = self.concept("Progressió final")
        relation = create_knowledge_relation(
            author=self.author,
            source=source,
            target=target,
            relation_type=KnowledgeRelation.RelationType.PROGRESSES_TO,
        )

        with self.assertRaises(ValidationError):
            transition_knowledge_relation(
                user=self.reviewer_user,
                relation=relation,
                target_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            )

        for concept in (source, target):
            transition_knowledge_concept(
                user=self.reviewer_user,
                concept=concept,
                target_status=KnowledgeConcept.EditorialStatus.VALIDATED,
                reason="Revisió professional inicial.",
            )
        transition_knowledge_relation(
            user=self.reviewer_user,
            relation=relation,
            target_status=KnowledgeRelation.EditorialStatus.VALIDATED,
            reason="Direcció i justificació revisades.",
        )

        relation.refresh_from_db()
        self.assertEqual(relation.last_validated_by, self.reviewer)
        self.assertIsNotNone(relation.last_validated_at)
        self.assertEqual(KnowledgeEditorialEvent.objects.count(), 3)
        event = KnowledgeEditorialEvent.objects.filter(
            target_model="iatrain.knowledgerelation",
            target_id=relation.pk,
        ).get()
        self.assertEqual(event.decided_by, self.reviewer)
        self.assertEqual(event.snapshot["relation_type"], "progresses_to")

    def test_model_save_cannot_bypass_endpoint_validation(self):
        source = self.concept("Origen encara esborrany")
        target = self.concept("Destí encara esborrany")

        with self.assertRaises(ValidationError):
            KnowledgeRelation.objects.create(
                source=source,
                target=target,
                relation_type=KnowledgeRelation.RelationType.REQUIRES,
                editorial_status=KnowledgeRelation.EditorialStatus.VALIDATED,
                authored_by=self.author,
            )

    def test_validated_content_must_be_reopened_before_editing(self):
        concept = self.concept("Contingut estable")
        transition_knowledge_concept(
            user=self.reviewer_user,
            concept=concept,
            target_status=KnowledgeConcept.EditorialStatus.VALIDATED,
        )
        concept.refresh_from_db()
        concept.description = "Canvi silenciós."

        with self.assertRaises(ValidationError):
            concept.full_clean()

        transition_knowledge_concept(
            user=self.reviewer_user,
            concept=concept,
            target_status=KnowledgeConcept.EditorialStatus.DRAFT,
            reason="Cal revisar una descripció nova.",
        )
        concept.refresh_from_db()
        concept.description = "Canvi revisable."
        concept.full_clean()
        concept.save()

    def test_governed_concepts_cannot_be_deleted_directly(self):
        concept = self.concept("Historial protegit")

        with self.assertRaises(ValidationError):
            concept.delete()

    def test_validated_concept_cannot_reopen_before_its_validated_relations(self):
        source = self.concept("Node amb dependència")
        target = self.concept("Node dependent")
        for concept in (source, target):
            transition_knowledge_concept(
                user=self.reviewer_user,
                concept=concept,
                target_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            )
        relation = create_knowledge_relation(
            author=self.author,
            source=source,
            target=target,
            relation_type=KnowledgeRelation.RelationType.REQUIRES,
        )
        transition_knowledge_relation(
            user=self.reviewer_user,
            relation=relation,
            target_status=KnowledgeRelation.EditorialStatus.VALIDATED,
        )

        with self.assertRaises(ValidationError):
            transition_knowledge_concept(
                user=self.reviewer_user,
                concept=source,
                target_status=KnowledgeConcept.EditorialStatus.DRAFT,
            )

    def test_rotation_validation_requires_validated_element_and_complete_segments(self):
        element = self.concept("Doble mortal")
        rotation = ElementRotation.objects.create(
            element=element,
            transverse_quarters=8,
            transverse_direction=ElementRotation.Direction.FORWARD,
            authored_by=self.author,
        )
        ElementRotationSegment.objects.create(
            rotation=rotation,
            sequence_index=1,
            longitudinal_half_turns=0,
        )

        with self.assertRaises(ValidationError):
            transition_element_rotation(
                user=self.reviewer_user,
                rotation=rotation,
                target_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            )

        transition_knowledge_concept(
            user=self.reviewer_user,
            concept=element,
            target_status=KnowledgeConcept.EditorialStatus.VALIDATED,
        )
        with self.assertRaises(ValidationError):
            transition_element_rotation(
                user=self.reviewer_user,
                rotation=rotation,
                target_status=KnowledgeConcept.EditorialStatus.VALIDATED,
            )

        ElementRotationSegment.objects.create(
            rotation=rotation,
            sequence_index=2,
            longitudinal_half_turns=0,
        )
        transition_element_rotation(
            user=self.reviewer_user,
            rotation=rotation,
            target_status=KnowledgeConcept.EditorialStatus.VALIDATED,
        )
        rotation.refresh_from_db()
        self.assertEqual(rotation.editorial_status, KnowledgeConcept.EditorialStatus.VALIDATED)
        self.assertEqual(rotation.last_validated_by, self.reviewer)

    def test_vocabulary_is_normalized_and_known_edge_domains_are_enforced(self):
        element = self.concept("  Barani   agrupat  ")
        position = self.concept("Posició agrupada", kind=KnowledgeConcept.Kind.BODY_POSITION)
        element.refresh_from_db()
        self.assertEqual(element.name, "Barani agrupat")
        self.assertEqual(element.kind, "skill")
        self.assertEqual(element.discipline, "trampoline")

        invalid = KnowledgeRelation(
            source=position,
            target=element,
            relation_type=" HAS-DEFINING-POSITION ",
            authored_by=self.author,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()
