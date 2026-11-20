"""Deterministic evaluation harness for local fake retrieval and answers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Callable

from .fixtures import load_fixtures

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "evaluation" / "cases.json"
REFUSAL = "I cannot answer from the permitted demo sources."
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "does",
    "how",
    "is",
    "of",
    "say",
    "the",
    "to",
    "what",
}


class EvaluationConfigError(ValueError):
    """Raised when an evaluation fixture does not match the local contract."""


@dataclass(frozen=True)
class ExpectedAnswer:
    refused: bool
    required_terms: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    persona_id: str
    allowed_roles: tuple[str, ...]
    allowed_source_ids: tuple[str, ...]
    expected_source_ids: tuple[str, ...]
    expected_answer: ExpectedAnswer


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationConfigError(f"{field} must be a non-empty string")
    return value.strip()


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise EvaluationConfigError(f"{field} must be a list of strings")
    result = tuple(_string(item, field) for item in value)
    if len(result) != len(set(result)):
        raise EvaluationConfigError(f"{field} must not contain duplicates")
    return result


def load_cases(path: str | Path = DEFAULT_CASES) -> list[EvaluationCase]:
    """Load and validate a versioned JSON evaluation set."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationConfigError(f"Cannot load evaluation cases from {path}: {error}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise EvaluationConfigError("evaluation schema_version must be 1")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise EvaluationConfigError("cases must be a non-empty list")

    cases = []
    seen_ids = set()
    for index, raw in enumerate(raw_cases):
        prefix = f"cases[{index}]"
        if not isinstance(raw, dict):
            raise EvaluationConfigError(f"{prefix} must be an object")
        case_id = _string(raw.get("id"), f"{prefix}.id")
        if case_id in seen_ids:
            raise EvaluationConfigError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)
        expected = raw.get("expected_answer")
        if not isinstance(expected, dict) or not isinstance(expected.get("refused"), bool):
            raise EvaluationConfigError(f"{prefix}.expected_answer.refused must be boolean")
        case = EvaluationCase(
            case_id=case_id,
            question=_string(raw.get("question"), f"{prefix}.question"),
            persona_id=_string(raw.get("persona_id"), f"{prefix}.persona_id"),
            allowed_roles=_string_list(raw.get("allowed_roles"), f"{prefix}.allowed_roles"),
            allowed_source_ids=_string_list(
                raw.get("allowed_source_ids"), f"{prefix}.allowed_source_ids"
            ),
            expected_source_ids=_string_list(
                raw.get("expected_source_ids"), f"{prefix}.expected_source_ids"
            ),
            expected_answer=ExpectedAnswer(
                refused=expected["refused"],
                required_terms=_string_list(
                    expected.get("required_terms"),
                    f"{prefix}.expected_answer.required_terms",
                ),
            ),
        )
        if not set(case.expected_source_ids).issubset(case.allowed_source_ids):
            raise EvaluationConfigError(
                f"{prefix}.expected_source_ids must be allowed by allowed_source_ids"
            )
        cases.append(case)
    return cases


class FakeRetriever:
    """Keyword retriever used only to make the evaluation suite executable offline."""

    def __init__(self, documents: list[dict]):
        self.documents = documents

    def search(self, question: str) -> list[dict]:
        terms = set(re.findall(r"[a-z0-9]+", question.lower())) - STOP_WORDS
        ranked = []
        for document in self.documents:
            text = f"{document['title']} {document['text']}".lower()
            score = sum(term in text for term in terms)
            if score:
                ranked.append((score, document["id"], document))
        return [document for _, _, document in sorted(ranked, key=lambda item: (-item[0], item[1]))]


class FakeAnswerProvider:
    """Deterministic answer provider with explicit citations and refusal output."""

    def answer(self, documents: list[dict]) -> dict:
        if not documents:
            return {"refused": True, "answer": REFUSAL, "sources": [], "citations": []}
        document = documents[0]
        return {
            "refused": False,
            "answer": f"{document['text']} [{document['id']}]",
            "sources": [{"id": document["id"], "title": document["title"]}],
            "citations": [document["id"]],
        }


class FakeEvaluationTarget:
    """Evaluation-only target; it is not wired to the public demo or service endpoint."""

    def __init__(self):
        _, documents = load_fixtures()
        self.retriever = FakeRetriever(documents)
        self.answer_provider = FakeAnswerProvider()

    def run(self, case: EvaluationCase) -> dict:
        candidates = self.retriever.search(case.question)
        permitted = [
            document for document in candidates if case.persona_id in document["audience"]
        ]
        return self.answer_provider.answer(permitted)


def _source_ids(response: dict) -> tuple[list[str], bool]:
    sources = response.get("sources", [])
    if not isinstance(sources, list):
        return [], False
    source_ids = []
    valid = True
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("id"), str):
            valid = False
            continue
        source_ids.append(source["id"])
    return source_ids, valid


def evaluate_case(case: EvaluationCase, response: dict) -> dict:
    failures = []
    if not isinstance(response, dict):
        response = {}
        failures.append("response_not_an_object")
    refused = response.get("refused") is True
    answer = response.get("answer") if isinstance(response.get("answer"), str) else ""
    if not answer.strip():
        failures.append("empty_answer")
    source_ids, sources_valid = _source_ids(response)
    if not sources_valid:
        failures.append("sources_not_a_list_of_id_objects")
    citations = response.get("citations", [])
    if not isinstance(citations, list) or not all(isinstance(item, str) for item in citations):
        citations = []
        failures.append("citations_not_a_string_list")

    if refused != case.expected_answer.refused:
        failures.append("expected_refusal" if case.expected_answer.refused else "unexpected_refusal")
    allowed = set(case.allowed_source_ids)
    for source_id in source_ids:
        if source_id not in allowed:
            failures.append(f"source_not_allowed:{source_id}")
    for source_id in citations:
        if source_id not in allowed:
            failures.append(f"citation_not_allowed:{source_id}")
        if source_id not in source_ids:
            failures.append(f"citation_without_source:{source_id}")
    expected = set(case.expected_source_ids)
    actual = set(source_ids)
    for source_id in sorted(expected - actual):
        failures.append(f"missing_source:{source_id}")
    for source_id in sorted(actual - expected):
        failures.append(f"unexpected_source:{source_id}")
    if not case.expected_answer.refused:
        for source_id in sorted(expected - set(citations)):
            failures.append(f"missing_citation:{source_id}")
    elif source_ids or citations:
        failures.append("refusal_contains_evidence")
    normalized_answer = answer.lower()
    for term in case.expected_answer.required_terms:
        if term.lower() not in normalized_answer:
            failures.append(f"missing_answer_term:{term}")

    return {
        "id": case.case_id,
        "persona_id": case.persona_id,
        "passed": not failures,
        "failures": failures,
        "actual": {
            "refused": refused,
            "source_ids": source_ids,
            "citation_ids": citations,
        },
    }


def run_evaluation(
    cases: list[EvaluationCase],
    target: Callable[[EvaluationCase], dict] | None = None,
) -> dict:
    """Run all cases and return a deterministic machine-readable report."""
    if target is None:
        target = FakeEvaluationTarget().run
    results = [evaluate_case(case, target(case)) for case in cases]
    failed = sum(not result["passed"] for result in results)
    return {
        "schema_version": 1,
        "summary": {"total": len(results), "passed": len(results) - failed, "failed": failed},
        "cases": results,
    }


def render_summary(report: dict) -> str:
    lines = []
    for result in report["cases"]:
        status = "PASS" if result["passed"] else "FAIL"
        details = "" if result["passed"] else f" — {', '.join(result['failures'])}"
        lines.append(
            f"{status} {result['id']} role={result['persona_id']} "
            f"sources={result['actual']['source_ids']}{details}"
        )
    summary = report["summary"]
    lines.append(
        f"Evaluation: {summary['passed']}/{summary['total']} passed, {summary['failed']} failed."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_evaluation(load_cases(args.cases))
    except EvaluationConfigError as error:
        parser.error(str(error))
    print(render_summary(report))
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
