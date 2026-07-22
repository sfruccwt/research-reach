"""Search CLI: one isolated Agent Reach Worker per confirmed topic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .common import atomic_write_json, atomic_write_text, canonical_hash, emit, fail, load_json, public_path, workdir_path
from .contracts import MANIFEST_SCHEMA, brief_hash, load_brief, load_evidence_jsonl, normalize_evidence, topic_map
from .config import model_name
from .errors import ResearchReachError, invalid
from .model_runner import run_codex_json


SEARCH_WORKER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["status", "evidence", "blocking_questions", "errors"],
    "properties": {
        "status": {"type": "string", "enum": ["ok", "partial", "blocked", "failed"]},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "question_refs",
                    "title",
                    "url",
                    "text",
                    "evidence_kind",
                    "source_name",
                    "retrieved_at",
                ],
                "properties": {
                    "question_refs": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "text": {"type": "string"},
                    "evidence_kind": {"type": "string", "enum": ["search_snippet", "fetched_content", "metadata"]},
                    "source_name": {"type": ["string", "null"]},
                    "retrieved_at": {"type": ["string", "null"]},
                },
            },
        },
        "blocking_questions": {"type": "array", "items": {"type": "string"}},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "message"],
                "properties": {"code": {"type": "string"}, "message": {"type": "string"}},
            },
        },
    },
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-reach-search")
    commands = parser.add_subparsers(dest="action", required=True)
    launch = commands.add_parser("launch", help="Launch one isolated search Worker per topic")
    launch.add_argument("--workdir", required=True)
    launch.add_argument("--topic", action="append", dest="topics")
    launch.add_argument("--fixture", help=argparse.SUPPRESS)
    return parser


def _worker_prompt(topic: Mapping[str, Any]) -> str:
    return (
        "You are an isolated Research Reach Search Worker. Do not launch another agent or call any "
        "research-reach-* command. Use $agent-reach for ordinary public retrieval and its Web Access "
        "escalation only when a confirmed source requires a real browser or login state. Stay inside the confirmed topic, "
        "cover its question refs, obey every prohibited action, and stop at the stated condition. Return "
        "only structured evidence. Evidence text must be a source-supported excerpt or concise factual "
        "summary, never hidden reasoning. Record exact public HTTP(S) URLs. For evidence read from a "
        "confirmed local artifact in the work directory, use an artifact://<relative-name> URL with "
        "evidence_kind metadata; never use file:// URLs or absolute local paths.\n\nConfirmed topic:\n"
        + json.dumps(topic, ensure_ascii=False, indent=2)
    )


def _fixture_result(path: str, topic_ref: str) -> dict[str, Any]:
    value = load_json(Path(path))
    if not isinstance(value, dict):
        raise invalid("search fixture must be an object")
    selected = value.get(topic_ref, value)
    if not isinstance(selected, dict):
        raise invalid(f"search fixture has no object for {topic_ref}")
    return selected


def _run_topic(workdir: Path, topic: Mapping[str, Any], fixture: str | None) -> dict[str, Any]:
    if fixture:
        return _fixture_result(fixture, str(topic["topic_ref"]))
    return run_codex_json(
        prompt=_worker_prompt(topic),
        schema=SEARCH_WORKER_SCHEMA,
        model=model_name("search"),
        workdir=workdir,
        worker_mode="search",
        network=True,
        timeout_seconds=900,
    )


def _validate_worker_result(value: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]], list[str], list[dict[str, str]]]:
    status = value.get("status")
    if status not in {"ok", "partial", "blocked", "failed"}:
        raise invalid("Search Worker status is invalid")
    evidence = value.get("evidence")
    questions = value.get("blocking_questions")
    errors = value.get("errors")
    if not isinstance(evidence, list) or any(not isinstance(item, Mapping) for item in evidence):
        raise invalid("Search Worker evidence must be an array of objects")
    if not isinstance(questions, list) or any(not isinstance(item, str) for item in questions):
        raise invalid("Search Worker blocking_questions must be strings")
    if not isinstance(errors, list) or any(not isinstance(item, dict) for item in errors):
        raise invalid("Search Worker errors must be objects")
    public_errors: list[dict[str, str]] = []
    for item in errors:
        code = item.get("code")
        message = item.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            raise invalid("Search Worker error fields must be strings")
        public_errors.append({"code": code[:120], "message": message[:500]})
    return status, evidence, list(questions), public_errors


def _merge_topic(
    workdir: Path,
    brief_digest: str,
    topic: Mapping[str, Any],
    worker_result: Mapping[str, Any],
) -> dict[str, Any]:
    topic_ref = str(topic["topic_ref"])
    status, raw_evidence, blocking_questions, errors = _validate_worker_result(worker_result)
    root = workdir / "artifacts" / "search" / topic_ref
    evidence_path = root / "evidence.jsonl"
    manifest_path = root / "manifest.json"
    existing: list[dict[str, Any]] = []
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
        if isinstance(manifest, dict) and manifest.get("brief_sha256") == brief_digest:
            candidate_existing = load_evidence_jsonl(evidence_path)
            if manifest.get("evidence_sha256") == canonical_hash(candidate_existing):
                existing = candidate_existing
    normalized = [normalize_evidence(item, topic) for item in raw_evidence]
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_content: set[str] = set()
    for item in [*existing, *normalized]:
        evidence_id = str(item.get("evidence_id", ""))
        content_fingerprint = canonical_hash({key: item.get(key) for key in ("topic_ref", "question_refs", "url", "text")})
        if evidence_id in seen_ids or content_fingerprint in seen_content:
            continue
        seen_ids.add(evidence_id)
        seen_content.add(content_fingerprint)
        merged.append(item)
    lines = "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in merged)
    atomic_write_text(evidence_path, lines)
    evidence_sha256 = canonical_hash(merged)
    covered = sorted({ref for item in merged for ref in item.get("question_refs", [])})
    expected = [item["question_ref"] for item in topic["search_plan"]["questions"]]
    uncovered = [ref for ref in expected if ref not in covered]
    effective_status = status
    if status == "ok" and uncovered:
        effective_status = "partial"
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "brief_sha256": brief_digest,
        "topic_ref": topic_ref,
        "status": effective_status,
        "evidence_count": len(merged),
        "evidence_sha256": evidence_sha256,
        "covered_question_refs": covered,
        "uncovered_question_refs": uncovered,
        "blocking_questions": blocking_questions,
        "errors": errors,
        "evidence_ref": f"artifacts/search/{topic_ref}/evidence.jsonl",
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "status": effective_status,
        "topic_ref": topic_ref,
        "artifact_refs": [manifest["evidence_ref"], f"artifacts/search/{topic_ref}/manifest.json"],
        "artifact_paths": [public_path(evidence_path), public_path(manifest_path)],
        "evidence_count": len(merged),
        "covered_question_refs": covered,
        "blocking_questions": blocking_questions,
        "errors": errors,
    }


def launch(workdir: Path, selected_topics: list[str] | None, fixture: str | None) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    brief = load_brief(workdir / "brief.json", require_confirmed=True)
    topics = topic_map(brief)
    requested = selected_topics or list(topics)
    if not requested or any(ref not in topics for ref in requested):
        raise invalid("--topic must identify confirmed brief topics")
    if len(requested) != len(set(requested)):
        raise invalid("--topic values must be unique")
    results: list[dict[str, Any]] = []
    public_errors: list[dict[str, Any]] = []
    digest = brief_hash(brief)
    for topic_ref in requested:
        try:
            worker_result = _run_topic(workdir, topics[topic_ref], fixture)
            result = _merge_topic(workdir, digest, topics[topic_ref], worker_result)
            results.append(result)
            public_errors.extend(result["errors"])
        except ResearchReachError as exc:
            results.append({
                "status": exc.status,
                "topic_ref": topic_ref,
                "artifact_refs": [],
                "artifact_paths": [],
                "evidence_count": 0,
                "covered_question_refs": [],
                "blocking_questions": [],
                "errors": [{"code": exc.code, "message": exc.message}],
            })
            public_errors.append({"code": exc.code, "message": exc.message, "topic_ref": topic_ref})
    statuses = {item["status"] for item in results}
    overall = "failed" if "failed" in statuses else "blocked" if "blocked" in statuses else "partial" if "partial" in statuses else "ok"
    return overall, {"brief_sha256": digest, "topics": results}, public_errors


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = "search-launch"
    try:
        status, data, errors = launch(workdir_path(args.workdir), args.topics, args.fixture)
        return emit(command, status, data, errors)
    except Exception as exc:
        return fail(command, exc)


if __name__ == "__main__":
    raise SystemExit(main())
