"""Tests for the deterministic local evaluation harness."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from reference_service.evaluation import (
    DEFAULT_CASES,
    evaluate_case,
    load_cases,
    main,
    run_evaluation,
)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = load_cases(DEFAULT_CASES)

    def test_default_fake_target_passes_versioned_cases(self):
        report = run_evaluation(self.cases)
        self.assertEqual({"total": 3, "passed": 3, "failed": 0}, report["summary"])
        self.assertTrue(all(result["passed"] for result in report["cases"]))

    def test_restricted_source_and_citation_are_reported(self):
        denied_case = next(case for case in self.cases if case.expected_answer.refused)
        response = {
            "refused": False,
            "answer": "The finance forecast is growing.",
            "sources": [{"id": "doc-finance-forecast", "title": "Finance forecast"}],
            "citations": ["doc-finance-forecast"],
        }
        result = evaluate_case(denied_case, response)
        self.assertFalse(result["passed"])
        self.assertIn("expected_refusal", result["failures"])
        self.assertIn("source_not_allowed:doc-finance-forecast", result["failures"])
        self.assertIn("citation_not_allowed:doc-finance-forecast", result["failures"])
        self.assertIn("refusal_contains_evidence", result["failures"])

    def test_confident_answer_for_no_access_case_fails(self):
        denied_case = next(case for case in self.cases if case.expected_answer.refused)
        result = evaluate_case(
            denied_case,
            {"refused": False, "answer": "Everything is fine.", "sources": [], "citations": []},
        )
        self.assertFalse(result["passed"])
        self.assertIn("expected_refusal", result["failures"])

    def test_malformed_evidence_cannot_pass_as_an_empty_refusal(self):
        denied_case = next(case for case in self.cases if case.expected_answer.refused)
        result = evaluate_case(
            denied_case,
            {
                "refused": True,
                "answer": "I cannot answer.",
                "sources": ["doc-finance-forecast"],
                "citations": [],
            },
        )
        self.assertFalse(result["passed"])
        self.assertIn("sources_not_a_list_of_id_objects", result["failures"])

    def test_citation_must_have_a_matching_source_object(self):
        allowed_case = next(case for case in self.cases if not case.expected_answer.refused)
        result = evaluate_case(
            allowed_case,
            {
                "refused": False,
                "answer": "documented code reviews",
                "sources": [],
                "citations": ["doc-eng-handbook"],
            },
        )
        self.assertFalse(result["passed"])
        self.assertIn("citation_without_source:doc-eng-handbook", result["failures"])

    def test_cli_writes_machine_report_and_human_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "evaluation.json"
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--cases", str(DEFAULT_CASES), "--json-report", str(report_path)])
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(0, code)
        self.assertIn("Evaluation: 3/3 passed, 0 failed.", output.getvalue())
        self.assertEqual(0, report["summary"]["failed"])
        self.assertEqual(
            {"id", "persona_id", "passed", "failures", "actual"},
            set(report["cases"][0]),
        )


if __name__ == "__main__":
    unittest.main()
