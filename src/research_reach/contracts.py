"""File contracts shared by Opening, Search, and Synthesis."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .common import atomic_write_json, canonical_hash, load_json, string_list, text, utc_now
from .errors import blocked, invalid


BRIEF_SCHEMA = "research-reach.brief/v1"
EVIDENCE_SCHEMA = "research-reach.evidence/v1"
MANIFEST_SCHEMA = "research-reach.search-manifest/v1"
REPORT_SCHEMA = "research-reach.report/v1"


def validate_topics(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise invalid("topics must be a non-empty array")
    topics: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    for index, raw in enumerate(value, 1):
        if not isinstance(raw, Mapping):
            raise invalid(f"topics[{index}] must be an object")
        topic_ref = text(raw.get("topic_ref"), f"topics[{index}].topic_ref")
        if topic_ref in seen_topics:
            raise invalid(f"duplicate topic_ref: {topic_ref}")
        seen_topics.add(topic_ref)
        inquiry = raw.get("inquiry_shape")
        scope = raw.get("scope_boundary")
        output = raw.get("output_contract")
        search = raw.get("search_plan")
        if not all(isinstance(item, Mapping) for item in (inquiry, scope, output, search)):
            raise invalid(f"topics[{index}] is missing a structured inquiry, scope, output, or search plan")
        normalized_questions: list[dict[str, str]] = []
        questions = search.get("questions")
        if not isinstance(questions, list) or not questions:
            raise invalid(f"topics[{index}].search_plan.questions must not be empty")
        seen_questions: set[str] = set()
        for q_index, question in enumerate(questions, 1):
            if not isinstance(question, Mapping):
                raise invalid(f"topics[{index}].search_plan.questions[{q_index}] must be an object")
            question_ref = text(question.get("question_ref"), "question_ref")
            if question_ref in seen_questions:
                raise invalid(f"duplicate question_ref in {topic_ref}: {question_ref}")
            seen_questions.add(question_ref)
            normalized_questions.append({"question_ref": question_ref, "question": text(question.get("question"), "question")})
        topics.append({
            "topic_ref": topic_ref,
            "inquiry_shape": {
                "research_object": text(inquiry.get("research_object"), "research_object"),
                "operation_type": text(inquiry.get("operation_type"), "operation_type"),
            },
            "research_goal": text(raw.get("research_goal"), "research_goal"),
            "scope_boundary": {
                "in_scope": string_list(scope.get("in_scope"), "in_scope"),
                "out_of_scope": string_list(scope.get("out_of_scope"), "out_of_scope"),
                "action_in_scope": string_list(scope.get("action_in_scope"), "action_in_scope"),
                "action_out_of_scope": string_list(scope.get("action_out_of_scope"), "action_out_of_scope"),
            },
            "output_contract": {
                "audience": text(output.get("audience"), "audience"),
                "product_shape": text(output.get("product_shape"), "product_shape"),
            },
            "search_plan": {
                "questions": normalized_questions,
                "source_surfaces": string_list(search.get("source_surfaces"), "source_surfaces", allow_empty=False),
                "stop_when": text(search.get("stop_when"), "stop_when"),
            },
        })
    return topics


def brief_content(brief: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": brief.get("schema_version"),
        "revision": brief.get("revision"),
        "request": brief.get("request"),
        "topics": brief.get("topics"),
    }


def brief_hash(brief: Mapping[str, Any]) -> str:
    return canonical_hash(brief_content(brief))


def new_brief(raw_input_full: str, topics: Any, *, revision: int = 1) -> dict[str, Any]:
    normalized = validate_topics(topics)
    return {
        "schema_version": BRIEF_SCHEMA,
        "revision": revision,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "request": {"raw_input_full": text(raw_input_full, "raw_input_full")},
        "topics": normalized,
        "approval": {
            "status": "pending_confirmation",
            "content_sha256": None,
            "confirmed_at": None,
        },
    }


def write_brief(path: Path, brief: dict[str, Any]) -> None:
    brief["updated_at"] = utc_now()
    atomic_write_json(path, brief)


def load_brief(path: Path, *, require_confirmed: bool = False) -> dict[str, Any]:
    value = load_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != BRIEF_SCHEMA:
        raise invalid("brief.json has an unsupported schema")
    if not isinstance(value.get("revision"), int) or value["revision"] < 1:
        raise invalid("brief revision must be a positive integer")
    request = value.get("request")
    if not isinstance(request, Mapping):
        raise invalid("brief request is missing")
    text(request.get("raw_input_full"), "raw_input_full")
    value["topics"] = validate_topics(value.get("topics"))
    approval = value.get("approval")
    if not isinstance(approval, Mapping) or approval.get("status") not in {"pending_confirmation", "confirmed"}:
        raise invalid("brief approval is invalid")
    if require_confirmed:
        if approval.get("status") != "confirmed":
            raise blocked("brief.json has not been confirmed")
        if approval.get("content_sha256") != brief_hash(value):
            raise blocked("brief.json changed after confirmation")
    return value


def topic_map(brief: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(topic["topic_ref"]): deepcopy(topic) for topic in brief["topics"]}


def normalize_evidence(raw: Mapping[str, Any], topic: Mapping[str, Any]) -> dict[str, Any]:
    topic_ref = str(topic["topic_ref"])
    allowed_questions = {item["question_ref"] for item in topic["search_plan"]["questions"]}
    question_refs = string_list(raw.get("question_refs"), "evidence.question_refs", allow_empty=False)
    if any(ref not in allowed_questions for ref in question_refs):
        raise invalid(f"evidence references a question outside {topic_ref}")
    url = text(raw.get("url"), "evidence.url")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise invalid("evidence.url must be an absolute HTTP(S) URL")
    evidence_kind = raw.get("evidence_kind")
    if evidence_kind not in {"search_snippet", "fetched_content", "metadata"}:
        raise invalid("evidence_kind is invalid")
    item = {
        "schema_version": EVIDENCE_SCHEMA,
        "topic_ref": topic_ref,
        "question_refs": list(dict.fromkeys(question_refs)),
        "title": text(raw.get("title"), "evidence.title"),
        "url": url,
        "text": text(raw.get("text"), "evidence.text"),
        "evidence_kind": evidence_kind,
        "source_name": str(raw.get("source_name", "")).strip() or None,
        "retrieved_at": str(raw.get("retrieved_at", "")).strip() or utc_now(),
    }
    fingerprint = canonical_hash({key: item[key] for key in ("topic_ref", "question_refs", "url", "text")})
    evidence_id = raw.get("evidence_id")
    item["evidence_id"] = evidence_id.strip() if isinstance(evidence_id, str) and evidence_id.strip() else f"ev-{fingerprint[:16]}"
    return item


def load_evidence_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    output: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise invalid(f"evidence file is unreadable: {path}") from exc
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise invalid(f"invalid evidence JSONL at line {index}: {path}") from exc
        if not isinstance(item, dict):
            raise invalid(f"evidence line {index} must be an object")
        output.append(item)
    return output
