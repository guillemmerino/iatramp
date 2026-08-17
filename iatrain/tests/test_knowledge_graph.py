import json

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from iatrain.models import KnowledgeConcept, KnowledgeRelation


class KnowledgeGraphViewTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="graph-admin",
            email="graph-admin@example.com",
            password="unused",
        )
        self.coach = get_user_model().objects.create_user(
            username="graph-coach",
            password="unused",
        )
        self.author = self.superuser.person
        self.source = KnowledgeConcept.objects.create(
            name="Salt agrupat",
            description="Element principal de prova.",
            kind=KnowledgeConcept.Kind.SKILL,
            authored_by=self.author,
            attributes={"legacy_sources": [{"legacy_id": 1}]},
        )
        self.target = KnowledgeConcept.objects.create(
            name="Mortal endavant agrupat",
            kind=KnowledgeConcept.Kind.SKILL,
            authored_by=self.author,
        )
        self.relation = KnowledgeRelation.objects.create(
            source=self.source,
            target=self.target,
            relation_type=KnowledgeRelation.RelationType.PROGRESSES_TO,
            rationale="Progressió tècnica de prova.",
            authored_by=self.author,
        )

    def post_status(self, url_name, object_id, status):
        return self.client.post(
            reverse(url_name, args=(object_id,)),
            data=json.dumps({"status": status}),
            content_type="application/json",
        )

    def test_graph_and_data_are_exclusive_to_superusers(self):
        protected_urls = (
            reverse("iatrain_knowledge_graph"),
            reverse("iatrain_knowledge_graph_data"),
        )

        for url in protected_urls:
            self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.coach)
        for url in protected_urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(
            self.post_status(
                "iatrain_knowledge_concept_status",
                self.source.pk,
                KnowledgeConcept.EditorialStatus.VALIDATED,
            ).status_code,
            403,
        )

    def test_superuser_sees_interactive_canvas_and_editorial_controls(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("iatrain_knowledge_graph"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="kg-canvas"')
        self.assertContains(response, 'id="kg-relation-filter"')
        self.assertContains(response, "Ctrl")
        self.assertContains(response, "Graf 3D")
        self.assertContains(response, 'data-status="validated"')

    def test_graph_data_serializes_nodes_relations_and_provenance(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("iatrain_knowledge_graph_data"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["nodes"]), 2)
        self.assertEqual(len(payload["links"]), 1)
        source = next(node for node in payload["nodes"] if node["id"] == self.source.pk)
        self.assertEqual(source["attributes"]["legacy_sources"][0]["legacy_id"], 1)
        self.assertEqual(payload["links"][0]["source"], self.source.pk)
        self.assertEqual(payload["links"][0]["target"], self.target.pk)

    def test_superuser_can_validate_a_concept_and_action_is_audited(self):
        self.client.force_login(self.superuser)

        response = self.post_status(
            "iatrain_knowledge_concept_status",
            self.source.pk,
            KnowledgeConcept.EditorialStatus.VALIDATED,
        )

        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.assertEqual(
            self.source.editorial_status,
            KnowledgeConcept.EditorialStatus.VALIDATED,
        )
        log_entry = LogEntry.objects.get(object_id=str(self.source.pk))
        self.assertEqual(log_entry.user, self.superuser)
        self.assertIn("draft a validated", log_entry.change_message)

    def test_relation_requires_both_concepts_to_be_validated(self):
        self.client.force_login(self.superuser)

        blocked = self.post_status(
            "iatrain_knowledge_relation_status",
            self.relation.pk,
            KnowledgeRelation.EditorialStatus.VALIDATED,
        )

        self.assertEqual(blocked.status_code, 400)
        self.assertIn("Valida primer", blocked.json()["error"])
        KnowledgeConcept.objects.filter(pk__in=(self.source.pk, self.target.pk)).update(
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED
        )

        accepted = self.post_status(
            "iatrain_knowledge_relation_status",
            self.relation.pk,
            KnowledgeRelation.EditorialStatus.VALIDATED,
        )

        self.assertEqual(accepted.status_code, 200)
        self.relation.refresh_from_db()
        self.assertEqual(
            self.relation.editorial_status,
            KnowledgeRelation.EditorialStatus.VALIDATED,
        )

    def test_concept_with_validated_relation_cannot_be_retired(self):
        KnowledgeConcept.objects.filter(pk__in=(self.source.pk, self.target.pk)).update(
            editorial_status=KnowledgeConcept.EditorialStatus.VALIDATED
        )
        self.relation.editorial_status = KnowledgeRelation.EditorialStatus.VALIDATED
        self.relation.save(update_fields=("editorial_status",))
        self.client.force_login(self.superuser)

        response = self.post_status(
            "iatrain_knowledge_concept_status",
            self.source.pk,
            KnowledgeConcept.EditorialStatus.RETIRED,
        )

        self.assertEqual(response.status_code, 400)
        self.source.refresh_from_db()
        self.assertEqual(
            self.source.editorial_status,
            KnowledgeConcept.EditorialStatus.VALIDATED,
        )

    def test_unknown_status_and_invalid_json_are_rejected(self):
        self.client.force_login(self.superuser)

        unknown = self.post_status(
            "iatrain_knowledge_concept_status",
            self.source.pk,
            "published",
        )
        invalid_json = self.client.post(
            reverse("iatrain_knowledge_concept_status", args=(self.source.pk,)),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(invalid_json.status_code, 400)
