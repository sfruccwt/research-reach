"""Synthesis CLI: isolated, networkless report generation from artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any

from .common import atomic_write_text, canonical_hash, emit, fail, load_json, public_path, workdir_path
from .contracts import REPORT_SCHEMA, brief_hash, load_brief, load_evidence_jsonl, topic_map
from .config import model_name
from .errors import blocked, invalid
from .model_runner import run_codex_json


SYNTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["report_markdown", "assessment", "used_urls"],
    "properties": {
        "report_markdown": {"type": "string", "minLength": 1},
        "assessment": {"type": "string", "enum": ["complete", "partial", "insufficient"]},
        "used_urls": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
        },
    },
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-reach-synthesis")
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("run", help="Generate report.md from confirmed artifacts")
    run.add_argument("--workdir", required=True)
    run.add_argument("--fixture", help=argparse.SUPPRESS)
    return parser


def _collect(workdir: Path, brief: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    digest = brief_hash(brief)
    evidence: list[dict[str, Any]] = []
    uncovered: list[str] = []
    for topic_ref, topic in topic_map(brief).items():
        root = workdir / "artifacts" / "search" / topic_ref
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            uncovered.extend(item["question_ref"] for item in topic["search_plan"]["questions"])
            continue
        manifest = load_json(manifest_path)
        if not isinstance(manifest, dict) or manifest.get("brief_sha256") != digest:
            raise blocked(f"search artifacts for {topic_ref} do not match the confirmed brief")
        items = load_evidence_jsonl(root / "evidence.jsonl")
        if manifest.get("evidence_sha256") != canonical_hash(items):
            raise blocked(f"search evidence for {topic_ref} changed after collection")
        evidence.extend(items)
        uncovered.extend(str(item) for item in manifest.get("uncovered_question_refs", []) if isinstance(item, str))
    return evidence, list(dict.fromkeys(uncovered))


def _prompt(brief: dict[str, Any], evidence: list[dict[str, Any]], uncovered: list[str]) -> str:
    allowed_public_urls = list(dict.fromkeys(
        str(item["url"])
        for item in evidence
        if isinstance(item.get("url"), str) and str(item["url"]).startswith(("http://", "https://"))
    ))
    return (
        "You are an isolated Research Reach Synthesis Worker with no network access. Use only the confirmed "
        "brief and supplied evidence. Produce a decision-ready Markdown report matching the audience and product "
        "shape. Distinguish sourced facts from analysis, preserve meaningful conflicts and limitations, and cite "
        "public sources with exact Markdown links. Refer to artifact:// evidence by its title, without turning its "
        "artifact URL into a Markdown link or including it in used_urls. Copy public URLs exactly from the allowed "
        "list below; do not add, remove, or normalize paths, fragments, query strings, or trailing slashes. Never "
        "invent a URL. If evidence is incomplete, say so "
        "and choose partial or insufficient. Return only the schema object.\n\nConfirmed brief:\n"
        + json.dumps(brief, ensure_ascii=False, indent=2)
        + "\n\nUncovered question refs:\n"
        + json.dumps(uncovered, ensure_ascii=False)
        + "\n\nAllowed public URLs:\n"
        + json.dumps(allowed_public_urls, ensure_ascii=False, indent=2)
        + "\n\nEvidence:\n"
        + json.dumps(evidence, ensure_ascii=False, indent=2)
    )


def _urls(markdown: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"https?://[^\s<>\]]+", markdown):
        value = match.group(0).rstrip("'\"),.;:!?")
        if value and value not in found:
            found.append(value)
    return found


def _quote(text: str) -> str:
    return "\n".join(">" if not line else f"> {line}" for line in text.splitlines())


def synthesize(workdir: Path, fixture: str | None) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    brief = load_brief(workdir / "brief.json", require_confirmed=True)
    evidence, uncovered = _collect(workdir, brief)
    if fixture:
        output = load_json(Path(fixture))
        if not isinstance(output, dict):
            raise invalid("synthesis fixture must be an object")
    else:
        output = run_codex_json(
            prompt=_prompt(brief, evidence, uncovered),
            schema=SYNTHESIS_SCHEMA,
            model=model_name("synthesis"),
            workdir=workdir,
            worker_mode="synthesis",
            network=False,
            ignore_rules=True,
            timeout_seconds=900,
        )
    markdown = output.get("report_markdown")
    assessment = output.get("assessment")
    used_urls = output.get("used_urls")
    if not isinstance(markdown, str) or not markdown.strip():
        raise invalid("Synthesis Worker report_markdown is invalid")
    if assessment not in {"complete", "partial", "insufficient"}:
        raise invalid("Synthesis Worker assessment is invalid")
    if not isinstance(used_urls, list) or any(not isinstance(url, str) for url in used_urls) or len(used_urls) != len(set(used_urls)):
        raise invalid("Synthesis Worker used_urls is invalid")
    allowed_urls = {str(item.get("url")) for item in evidence if isinstance(item.get("url"), str)}
    report_urls = _urls(markdown)
    unsupported_urls = sorted({url for url in [*used_urls, *report_urls] if url not in allowed_urls})
    if unsupported_urls:
        detail = ", ".join(unsupported_urls[:5])
        raise invalid(f"Synthesis Worker cited URL not present in evidence: {detail}")
    if set(used_urls) != set(report_urls):
        only_declared = sorted(set(used_urls) - set(report_urls))
        only_report = sorted(set(report_urls) - set(used_urls))
        raise invalid(
            "Synthesis Worker used_urls does not match report citations "
            f"(only in used_urls: {only_declared[:5]}; only in report: {only_report[:5]})"
        )
    if uncovered and assessment == "complete":
        assessment = "partial"
    digest = brief_hash(brief)
    frontmatter = (
        "---\n"
        f"schema: {REPORT_SCHEMA}\n"
        f"brief_sha256: {digest}\n"
        f"assessment: {assessment}\n"
        f"source_count: {len(used_urls)}\n"
        "---\n\n"
    )
    report = (
        frontmatter
        + "# Research Reach Report\n\n"
        + "## Original Request\n\n"
        + _quote(brief["request"]["raw_input_full"])
        + "\n\n## Research Result\n\n"
        + markdown.strip()
        + "\n"
    )
    report_path = workdir / "report.md"
    atomic_write_text(report_path, report)
    status = "ok" if assessment == "complete" else "partial"
    errors = [] if status == "ok" else [{"code": "INSUFFICIENT_EVIDENCE", "message": "report records incomplete evidence"}]
    data = {
        "brief_sha256": digest,
        "assessment": assessment,
        "report_ref": "report.md",
        "report_path": public_path(report_path),
        "source_count": len(used_urls),
        "evidence_count": len(evidence),
    }
    return status, data, errors


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = "synthesis-run"
    try:
        status, data, errors = synthesize(workdir_path(args.workdir), args.fixture)
        return emit(command, status, data, errors)
    except Exception as exc:
        return fail(command, exc)


if __name__ == "__main__":
    raise SystemExit(main())
