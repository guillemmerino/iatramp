import json
from importlib import import_module

from django.test import TestCase
from django.urls import reverse

from ...base import _BaseTrampoliDataMixin
from ....models.judging import JudgeDeviceToken, JudgePortalAssignment, JudgeScoreDraft, JudgeScoreSubmission
from ....models.scoring import ScoreEntry, ScoreRevision, ScoringSchema
from ....services.judging.supervision import validate_single_supervisor_per_field
from ....views.judge.admin import _validate_permission_row
from ....views.judge.permissions import _normalize_permissions


class JudgePermissionRoleContractTests(TestCase):
    def setUp(self):
        self.schema_by_code = {
            "E": {
                "label": "Execucio",
                "code": "E",
                "type": "matrix",
                "shape": "judge_x_item",
                "judges": {"count": 2},
                "items": {"count": 5},
                "decimals": 1,
                "crash": {"enabled": True},
            },
        }

    def test_permission_row_defaults_to_standard_role(self):
        permission = _validate_permission_row(
            self.schema_by_code,
            {
                "field_code": "E",
                "judge_index": 1,
                "item_start": 1,
                "item_count": "",
            },
        )

        self.assertEqual(permission["role"], "standard")

    def test_permission_row_accepts_supervisor_role(self):
        permission = _validate_permission_row(
            self.schema_by_code,
            {
                "field_code": "E",
                "judge_index": 1,
                "item_start": 1,
                "item_count": "",
                "role": "supervisor",
                "display_computed_codes": ["TOTAL", "EXEC"],
            },
        )

        self.assertEqual(permission["role"], "supervisor")
        self.assertEqual(permission["display_computed_codes"], ["TOTAL", "EXEC"])

    def test_permission_row_accepts_review_only_supervisor_without_judge_slot(self):
        permission = _validate_permission_row(
            self.schema_by_code,
            {
                "field_code": "E",
                "judge_index": 1,
                "item_start": 1,
                "item_count": "",
                "role": "supervisor",
                "supervisor_mode": "review_only",
            },
        )

        self.assertEqual(permission["supervisor_mode"], "review_only")
        self.assertNotIn("judge_index", permission)

    def test_runtime_permission_normalization_preserves_role(self):
        permissions = _normalize_permissions(
            [
                {"field_code": "E", "judge_index": 1},
                {"field_code": "E", "judge_index": 2, "role": "supervisor"},
            ]
        )

        self.assertEqual(permissions[0]["role"], "standard")
        self.assertEqual(permissions[1]["role"], "supervisor")
        self.assertEqual(permissions[1]["supervisor_mode"], "scoring")

    def test_runtime_permission_normalization_preserves_review_only_mode(self):
        permission = _normalize_permissions(
            [{"field_code": "E", "role": "supervisor", "supervisor_mode": "review_only"}]
        )[0]

        self.assertEqual(permission["role"], "supervisor")
        self.assertEqual(permission["supervisor_mode"], "review_only")


class JudgeSupervisionFlowTests(_BaseTrampoliDataMixin, TestCase):
    def setUp(self):
        self.client.raise_request_exception = False
        self.competicio = self._create_competicio("Comp supervisio jutges")
        self.aparell = self._create_aparell("TRA_SUP", "Trampoli supervisio")
        self.comp_aparell = self._create_comp_aparell(self.competicio, self.aparell)
        ScoringSchema.objects.create(
            aparell=self.aparell,
            schema={
                "fields": [
                    {
                        "label": "Execucio",
                        "code": "E",
                        "type": "matrix",
                        "shape": "judge_x_item",
                        "judges": {"count": 2},
                        "items": {"count": 5},
                        "decimals": 1,
                        "crash": {"enabled": True},
                    },
                ],
                "computed": [{"code": "TOTAL", "label": "Nota final", "formula": "0"}],
            },
        )
        self.inscripcio = self._create_inscripcio(self.competicio, "Gimnasta supervisat")
        self.standard_token = JudgeDeviceToken.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Jutge standard",
            permissions=[],
        )
        self.standard_assignment = JudgePortalAssignment.objects.create(
            judge_token=self.standard_token,
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Standard E1",
            ordre=1,
            permissions=[
                {
                    "field_code": "E",
                    "judge_index": 1,
                    "item_start": 1,
                    "item_count": None,
                    "role": "standard",
                }
            ],
        )
        self.supervisor_token = JudgeDeviceToken.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Supervisor E1",
            permissions=[],
        )
        self.supervisor_assignment = JudgePortalAssignment.objects.create(
            judge_token=self.supervisor_token,
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            label="Supervisor E1",
            ordre=1,
            permissions=[
                {
                    "field_code": "E",
                    "judge_index": 2,
                    "item_start": 1,
                    "item_count": None,
                    "role": "supervisor",
                    "display_computed_codes": ["TOTAL"],
                }
            ],
        )

    def _standard_submission_payload(self, values=None):
        values = values or [0.1, 0.2, 0.3, 0.4, 0.5]
        return {
            "assignment_id": self.standard_assignment.id,
            "inscripcio_id": self.inscripcio.id,
            "subject_kind": "inscripcio",
            "subject_id": self.inscripcio.id,
            "exercici": 1,
            "inputs_patch": {"E": values},
        }

    def test_standard_judge_with_supervisor_creates_pending_submission_not_score_entry(self):
        response = self.client.post(
            reverse("judge_save_partial", kwargs={"token": self.standard_token.id}),
            data=json.dumps(self._standard_submission_payload()),
            content_type="application/json",
        )

        self.assertNotEqual(
            response.status_code,
            500,
            "judge_save_partial returned 500; a supervised standard submission should create a pending "
            "JudgeScoreSubmission instead of crashing.",
        )
        self.assertIn(response.status_code, {200, 202}, response.content)
        data = response.json()
        self.assertEqual(data.get("publication_status"), "pending")
        self.assertTrue(data.get("requires_supervision"))
        self.assertTrue(data.get("pending_submission_ids"))
        self.assertFalse(
            ScoreEntry.objects.filter(
                competicio=self.competicio,
                comp_aparell=self.comp_aparell,
                inscripcio=self.inscripcio,
                exercici=1,
                fase__isnull=True,
            ).exists(),
            "A standard judge submission covered by a supervisor must stay pending and not publish ScoreEntry.",
        )
        submissions = JudgeScoreSubmission.objects.filter(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            submitted_by_token=self.standard_token,
            submitted_by_assignment=self.standard_assignment,
            subject_kind="inscripcio",
            subject_id=self.inscripcio.id,
            exercici=1,
            field_code="E",
            judge_index=1,
            status=JudgeScoreSubmission.Status.PENDING,
        )
        self.assertEqual(
            submissions.count(),
            1,
            "A standard judge submission covered by a supervisor must create exactly one pending JudgeScoreSubmission.",
        )
        submission = submissions.get()
        self.assertEqual(submission.inputs_patch, {"E": [0.1, 0.2, 0.3, 0.4, 0.5]})
        self.assertEqual(submission.normalized_inputs_patch.get("E"), [0.1, 0.2, 0.3, 0.4, 0.5])

    def test_standard_live_update_creates_draft_without_submission_or_score_entry(self):
        response = self.client.post(
            reverse("judge_draft_update", kwargs={"token": self.standard_token.id}),
            data=json.dumps({**self._standard_submission_payload(), "client_sequence": 1}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        draft = JudgeScoreDraft.objects.get(submitted_by_token=self.standard_token)
        self.assertEqual(draft.runtime_field_code, "E")
        self.assertEqual(
            draft.normalized_inputs_patch["E"]["__set_matrix__"],
            [[0, 0, 0.1], [0, 1, 0.2], [0, 2, 0.3], [0, 3, 0.4], [0, 4, 0.5]],
        )
        self.assertFalse(JudgeScoreSubmission.objects.exists())
        self.assertFalse(ScoreEntry.objects.exists())

    def test_supervisor_crash_is_live_for_standard_without_publishing(self):
        update_response = self.client.post(
            reverse("judge_draft_update", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "client_sequence": 1,
                "inputs_patch": {"__crash__E": [3, 3]},
            }),
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200, update_response.content)
        self.assertFalse(ScoreEntry.objects.exists())

        feed_response = self.client.get(
            reverse("judge_draft_updates", kwargs={"token": self.standard_token.id}),
            {"assignment_id": self.standard_assignment.id, "exercici": 1},
        )
        self.assertEqual(feed_response.status_code, 200, feed_response.content)
        drafts = feed_response.json()["drafts"]
        self.assertEqual(len(drafts), 1)
        self.assertEqual(
            drafts[0]["normalized_inputs_patch"]["__crash__E"]["__set_list__"],
            [[0, 3], [1, 3]],
        )

    def test_review_only_supervisor_crash_preserves_judge_presence(self):
        self.supervisor_assignment.permissions = [
            {
                "field_code": "E",
                "role": "supervisor",
                "supervisor_mode": "review_only",
            }
        ]
        self.supervisor_assignment.save(update_fields=["permissions", "updated_at"])

        response = self.client.post(
            reverse("judge_draft_update", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "client_sequence": 1,
                "inputs_patch": {"__crash__E": [0, 3]},
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        crash_patch = response.json()["drafts"][0]["normalized_inputs_patch"]["__crash__E"]
        self.assertEqual(crash_patch["__set_list__"], [[0, 3], [1, 3]])
        self.assertTrue(crash_patch["__preserve_presence__"])

    def test_supervisor_save_clears_live_drafts_and_records_supervisor_source(self):
        JudgeScoreDraft.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            fase=None,
            submitted_by_token=self.standard_token,
            submitted_by_assignment=self.standard_assignment,
            subject_kind="inscripcio",
            subject_id=self.inscripcio.id,
            exercici=1,
            field_code="E",
            runtime_field_code="E",
            judge_index=1,
            inputs_patch={"E": [0.6, 0.7, 0.8, 0.9, 1.0]},
            normalized_inputs_patch={"E": {"__set_matrix__": [[0, 0, 0.6]]}},
        )
        response = self.client.post(
            reverse("judge_save_partial", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {
                    "E": [
                        [0.6, 0.7, 0.8, 0.9, 1.0],
                        [0.1, 0.2, 0.3, 0.4, 0.5],
                    ],
                    "__crash__E": [3, 3],
                },
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(JudgeScoreDraft.objects.exists())
        self.assertEqual(ScoreRevision.objects.latest("id").source, ScoreRevision.Source.SUPERVISOR)

    def test_supervisor_snapshot_does_not_delete_a_newer_live_draft(self):
        draft = JudgeScoreDraft.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            submitted_by_token=self.standard_token,
            submitted_by_assignment=self.standard_assignment,
            subject_kind="inscripcio",
            subject_id=self.inscripcio.id,
            exercici=1,
            field_code="E",
            runtime_field_code="E",
            judge_index=1,
            inputs_patch={"E": [0.6, 0.7, 0.8, 0.9, 1.0]},
            normalized_inputs_patch={"E": {"__set_matrix__": [[0, 0, 0.6]]}},
            version=2,
        )
        response = self.client.post(
            reverse("judge_save_partial", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "captured_draft_versions": {str(draft.id): 1},
                "inputs_patch": {
                    "E": [
                        [0.6, 0.7, 0.8, 0.9, 1.0],
                        [0.1, 0.2, 0.3, 0.4, 0.5],
                    ],
                },
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(JudgeScoreDraft.objects.filter(pk=draft.pk, version=2).exists())

    def test_standard_judge_cannot_submit_supervisor_controlled_crash(self):
        payload = self._standard_submission_payload()
        payload["inputs_patch"]["__crash__E"] = [3, 3]

        response = self.client.post(
            reverse("judge_save_partial", kwargs={"token": self.standard_token.id}),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        submission = JudgeScoreSubmission.objects.get(submitted_by_token=self.standard_token)
        self.assertNotIn("__crash__E", submission.inputs_patch)
        self.assertNotIn("__crash__E", submission.normalized_inputs_patch)

    def test_supervisor_crash_is_synchronized_to_every_judge(self):
        response = self.client.post(
            reverse("judge_save_partial", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "inscripcio_id": self.inscripcio.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {
                    "E": [
                        [0.1, 0.2, 0.3, 0.4, 0.5],
                        [0.1, 0.2, 0.3, 0.4, 0.5],
                    ],
                    "__crash__E": [1, 3],
                },
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        entry = ScoreEntry.objects.get(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
        )
        self.assertEqual(entry.inputs["__crash__E"], [3, 3])

    def test_review_only_supervisor_publishes_without_creating_own_judge_presence(self):
        self.supervisor_assignment.permissions = [
            {
                "field_code": "E",
                "item_start": 1,
                "item_count": None,
                "role": "supervisor",
                "supervisor_mode": "review_only",
                "display_computed_codes": ["TOTAL"],
            }
        ]
        self.supervisor_assignment.save(update_fields=["permissions", "updated_at"])

        response = self.client.post(
            reverse("judge_save_partial", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {
                    "E": [[0.1, 0.2, 0.3, 0.4, 0.5], None],
                    "__crash__E": [0, 0],
                },
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        entry = ScoreEntry.objects.get(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
        )
        self.assertEqual(entry.inputs["__presence__E"], [True, False])
        self.assertEqual(entry.inputs["E"][0], [0.1, 0.2, 0.3, 0.4, 0.5])
        self.assertEqual(entry.inputs["E"][1], [None, None, None, None, None])
        self.assertEqual(entry.inputs["__crash__E"], [0, 0])

    def test_five_scoring_rows_plus_review_only_supervisor_stays_at_five_judges(self):
        schema_obj = ScoringSchema.objects.get(aparell=self.aparell)
        schema = dict(schema_obj.schema)
        schema["fields"] = [dict(field) for field in schema["fields"]]
        schema["fields"][0]["judges"] = {"count": 5}
        schema_obj.schema = schema
        schema_obj.save(update_fields=["schema"])
        self.supervisor_assignment.permissions = [
            {
                "field_code": "E",
                "role": "supervisor",
                "supervisor_mode": "review_only",
            }
        ]
        self.supervisor_assignment.save(update_fields=["permissions", "updated_at"])
        rows = [
            [round((judge + item + 1) / 10, 1) for item in range(5)]
            for judge in range(5)
        ]

        response = self.client.post(
            reverse("judge_save_partial", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {"E": rows, "__crash__E": [0, 0, 0, 0, 0]},
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        entry = ScoreEntry.objects.get(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
        )
        self.assertEqual(entry.inputs["__presence__E"], [True] * 5)
        self.assertEqual(len(entry.inputs["E"]), 5)
        self.assertEqual(entry.inputs["E"], rows)

    def test_supervisor_approval_publishes_pending_submission_to_score_entry(self):
        submission = JudgeScoreSubmission.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            fase=None,
            submitted_by_token=self.standard_token,
            submitted_by_assignment=self.standard_assignment,
            subject_kind="inscripcio",
            subject_id=self.inscripcio.id,
            exercici=1,
            field_code="E",
            runtime_field_code="E",
            judge_index=1,
            item_start=1,
            item_count=None,
            inputs_patch={"E": [0.6, 0.7, 0.8, 0.9, 1.0]},
            normalized_inputs_patch={"E": [0.6, 0.7, 0.8, 0.9, 1.0]},
            status=JudgeScoreSubmission.Status.PENDING,
        )

        approve = self._approval_service()
        try:
            approve(
                submission=submission,
                supervisor_token=self.supervisor_token,
                supervisor_assignment=self.supervisor_assignment,
            )
        except Exception as exc:  # pragma: no cover - failure output documents pending integration.
            self.fail(f"Approval service raised {type(exc).__name__}: {exc}")

        submission.refresh_from_db()
        self.assertEqual(submission.status, JudgeScoreSubmission.Status.APPROVED)
        self.assertEqual(submission.reviewed_by_token_id, self.supervisor_token.id)
        self.assertEqual(submission.reviewed_by_assignment_id, self.supervisor_assignment.id)
        self.assertIsNotNone(submission.reviewed_at)
        entry = ScoreEntry.objects.get(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
            fase__isnull=True,
        )
        self.assertEqual(entry.inputs["E"][0], [0.6, 0.7, 0.8, 0.9, 1.0])

    def test_duplicate_supervisor_in_same_permission_set_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "mes d'un supervisor"):
            validate_single_supervisor_per_field(
                competicio=self.competicio,
                comp_aparell=self.comp_aparell,
                phase=None,
                permissions=[
                    {"field_code": "E", "judge_index": 1, "role": "supervisor"},
                    {"field_code": "E", "judge_index": 2, "role": "supervisor"},
                ],
            )

    def test_supervisor_portal_exposes_integrated_pending_polling(self):
        response = self.client.get(
            reverse(
                "judge_portal_assignment",
                kwargs={"token": self.supervisor_token.id, "assignment_id": self.supervisor_assignment.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["permissions"][0]["display_computed_codes"], ["TOTAL"])
        self.assertContains(response, "SUPERVISION_PENDING_URL")
        self.assertContains(response, "loadSupervisionPendingIntegrated")
        self.assertContains(response, "expandedSupervisorPerms")
        self.assertContains(response, "renderSupervisorMatrix")
        self.assertContains(response, 'table.dataset.supervisorMatrix = "1"')
        self.assertContains(response, "judge-supervisor-row-head")
        self.assertContains(response, "data-supervisor-matrix-cell")
        self.assertContains(response, "judge-supervisor-item-crash")
        self.assertContains(response, "dataset.supervisorCrashButton")
        self.assertContains(response, "renderSupervisorComputedFields")
        self.assertContains(response, "Notes calculades")
        self.assertContains(response, "crash_supervisor_controlled")
        self.assertContains(response, "mergePendingPatchIntoDraft")
        self.assertContains(response, "DRAFT_UPDATE_URL")
        self.assertContains(response, "pollLiveDrafts")
        self.assertContains(response, "captured_draft_versions")
        self.assertContains(response, "applyRemoteCrashWithoutRerender")
        self.assertContains(response, "active.disabled")
        self.assertContains(response, "dataset.runtimeFieldCode")
        self.assertContains(response, "judge-fields-layout")
        self.assertContains(response, "grid-template-columns:repeat(12")
        self.assertContains(response, "table-layout:fixed")
        self.assertContains(response, 'classList.toggle("is-wide"')
        self.assertContains(response, 'input[type="number"]::-webkit-inner-spin-button')
        self.assertContains(response, 'input.type !== "number"')
        self.assertContains(response, 'evt.preventDefault()')
        self.assertTrue(response.context["judge_save_button_visible"])
        self.assertContains(response, 'data-judge-save-action="1"')
        self.assertNotContains(response, 'id="judgeSupervisionPanel"')

        standard_response = self.client.get(
            reverse(
                "judge_portal_assignment",
                kwargs={"token": self.standard_token.id, "assignment_id": self.standard_assignment.id},
            )
        )
        self.assertEqual(standard_response.status_code, 200)
        self.assertTrue(standard_response.context["permissions"][0]["crash_supervisor_controlled"])
        self.assertContains(standard_response, "Crash: encara no indicat pel supervisor")
        self.assertFalse(standard_response.context["judge_save_button_visible"])
        self.assertNotContains(standard_response, 'data-judge-save-action="1"')

    def test_standard_hybrid_portal_keeps_save_with_unsupervised_hint(self):
        schema_obj = ScoringSchema.objects.get(aparell=self.aparell)
        schema = dict(schema_obj.schema)
        schema["fields"] = list(schema.get("fields") or []) + [
            {"label": "Dificultat", "code": "D", "type": "number", "decimals": 1},
        ]
        schema_obj.schema = schema
        schema_obj.save(update_fields=["schema"])
        self.standard_assignment.permissions = list(self.standard_assignment.permissions) + [
            {"field_code": "D", "judge_index": 1, "role": "standard"},
        ]
        self.standard_assignment.save(update_fields=["permissions", "updated_at"])

        response = self.client.get(reverse(
            "judge_portal_assignment",
            kwargs={"token": self.standard_token.id, "assignment_id": self.standard_assignment.id},
        ))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["judge_save_button_visible"])
        self.assertTrue(response.context["judge_save_non_supervised_only"])
        self.assertContains(response, 'data-judge-save-action="1"')
        self.assertContains(response, "Només camps no supervisats")

    def test_standard_without_supervisor_keeps_normal_save_button(self):
        self.supervisor_assignment.is_active = False
        self.supervisor_assignment.save(update_fields=["is_active", "updated_at"])

        response = self.client.get(reverse(
            "judge_portal_assignment",
            kwargs={"token": self.standard_token.id, "assignment_id": self.standard_assignment.id},
        ))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["judge_save_button_visible"])
        self.assertFalse(response.context["judge_save_non_supervised_only"])
        self.assertContains(response, 'data-judge-save-action="1"')
        self.assertNotContains(response, "Només camps no supervisats")

    def test_supervisor_save_publishes_and_approves_other_pending_rows(self):
        submission = JudgeScoreSubmission.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            fase=None,
            submitted_by_token=self.standard_token,
            submitted_by_assignment=self.standard_assignment,
            subject_kind="inscripcio",
            subject_id=self.inscripcio.id,
            exercici=1,
            field_code="E",
            runtime_field_code="E",
            judge_index=1,
            item_start=1,
            item_count=None,
            inputs_patch={"E": [[0.6, 0.7, 0.8, 0.9, 1.0], []]},
            normalized_inputs_patch={"E": [[0.6, 0.7, 0.8, 0.9, 1.0], []]},
            status=JudgeScoreSubmission.Status.PENDING,
        )

        response = self.client.post(
            reverse("judge_save_partial", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "inscripcio_id": self.inscripcio.id,
                "subject_kind": "inscripcio",
                "subject_id": self.inscripcio.id,
                "exercici": 1,
                "inputs_patch": {
                    "E": [
                        [0.6, 0.7, 0.8, 0.9, 1.0],
                        [0.1, 0.2, 0.3, 0.4, 0.5],
                    ],
                },
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json().get("publication_status"), "published")
        submission.refresh_from_db()
        self.assertEqual(submission.status, JudgeScoreSubmission.Status.APPROVED)
        self.assertEqual(submission.reviewed_by_token_id, self.supervisor_token.id)
        entry = ScoreEntry.objects.get(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            inscripcio=self.inscripcio,
            exercici=1,
            fase__isnull=True,
        )
        self.assertEqual(entry.inputs["E"][0], [0.6, 0.7, 0.8, 0.9, 1.0])
        self.assertEqual(entry.inputs["E"][1], [0.1, 0.2, 0.3, 0.4, 0.5])

    def test_supervision_approve_requires_submission_id(self):
        response = self.client.post(
            reverse("judge_supervision_approve", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({"assignment_id": self.supervisor_assignment.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_supervision_approve_rejects_non_object_patch(self):
        submission = JudgeScoreSubmission.objects.create(
            competicio=self.competicio,
            comp_aparell=self.comp_aparell,
            fase=None,
            submitted_by_token=self.standard_token,
            submitted_by_assignment=self.standard_assignment,
            subject_kind="inscripcio",
            subject_id=self.inscripcio.id,
            exercici=1,
            field_code="E",
            runtime_field_code="E",
            judge_index=1,
            item_start=1,
            item_count=None,
            inputs_patch={"E": [0.6, 0.7, 0.8, 0.9, 1.0]},
            normalized_inputs_patch={"E": [0.6, 0.7, 0.8, 0.9, 1.0]},
            status=JudgeScoreSubmission.Status.PENDING,
        )

        response = self.client.post(
            reverse("judge_supervision_approve", kwargs={"token": self.supervisor_token.id}),
            data=json.dumps({
                "assignment_id": self.supervisor_assignment.id,
                "submission_id": submission.id,
                "inputs_patch": ["invalid"],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def _approval_service(self):
        try:
            module = import_module("competicions_trampoli.services.judging.submissions")
        except ModuleNotFoundError as exc:
            if exc.name == "competicions_trampoli.services.judging.submissions":
                self.fail(
                    "Pending integration: expected "
                    "competicions_trampoli.services.judging.submissions.approve_judge_score_submission"
                )
            raise
        approve = getattr(module, "approve_judge_score_submission", None)
        if approve is None:
            self.fail(
                "Pending integration: expected approve_judge_score_submission in "
                "competicions_trampoli.services.judging.submissions"
            )
        return approve
