"""Opening CLI: draft, revise, and confirm one reviewable brief."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .common import emit, fail, load_json, public_path, read_json_input, utc_now, workdir_path
from .contracts import BRIEF_SCHEMA, brief_hash, load_brief, new_brief, validate_topics, write_brief
from .config import model_name
from .errors import invalid
from .model_runner import run_codex_json


OPENING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["topics"],
    "properties": {
        "topics": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "topic_ref",
                    "inquiry_shape",
                    "research_goal",
                    "scope_boundary",
                    "output_contract",
                    "search_plan",
                ],
                "properties": {
                    "topic_ref": {"type": "string", "minLength": 1},
                    "inquiry_shape": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["research_object", "operation_type"],
                        "properties": {
                            "research_object": {"type": "string", "minLength": 1},
                            "operation_type": {"type": "string", "minLength": 1},
                        },
                    },
                    "research_goal": {"type": "string", "minLength": 1},
                    "scope_boundary": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["in_scope", "out_of_scope", "action_in_scope", "action_out_of_scope"],
                        "properties": {
                            key: {"type": "array", "items": {"type": "string", "minLength": 1}}
                            for key in ("in_scope", "out_of_scope", "action_in_scope", "action_out_of_scope")
                        },
                    },
                    "output_contract": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["audience", "product_shape"],
                        "properties": {
                            "audience": {"type": "string", "minLength": 1},
                            "product_shape": {"type": "string", "minLength": 1},
                        },
                    },
                    "search_plan": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["questions", "source_surfaces", "stop_when"],
                        "properties": {
                            "questions": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["question_ref", "question"],
                                    "properties": {
                                        "question_ref": {"type": "string", "minLength": 1},
                                        "question": {"type": "string", "minLength": 1},
                                    },
                                },
                            },
                            "source_surfaces": {
                                "type": "array",
                                "minItems": 1,
                                "items": {"type": "string", "minLength": 1},
                            },
                            "stop_when": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
        }
    },
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-reach-opening")
    commands = parser.add_subparsers(dest="action", required=True)
    draft = commands.add_parser("draft", help="Create a reviewable brief.json")
    draft.add_argument("--workdir", required=True)
    draft.add_argument("--input", required=True, help="JSON object/file/'-' containing raw_input_full")
    draft.add_argument("--force", action="store_true")
    draft.add_argument("--fixture", help=argparse.SUPPRESS)
    revise = commands.add_parser("revise", help="Revise brief.json from explicit feedback")
    revise.add_argument("--workdir", required=True)
    revise.add_argument("--input", required=True, help="JSON object/file/'-' containing feedback")
    revise.add_argument("--fixture", help=argparse.SUPPRESS)
    confirm = commands.add_parser("confirm", help="Confirm the exact current brief content")
    confirm.add_argument("--workdir", required=True)
    confirm.add_argument("--yes", action="store_true", help="Record explicit user confirmation")
    return parser


def _fixture_or_model(
    fixture: str | None,
    *,
    prompt: str,
    workdir: Path,
) -> dict[str, Any]:
    if fixture:
        value = load_json(Path(fixture))
        if not isinstance(value, dict):
            raise invalid("opening fixture must be an object")
        return value
    return run_codex_json(
        prompt=prompt,
        schema=OPENING_SCHEMA,
        model=model_name("opening"),
        workdir=workdir,
        worker_mode="opening",
        network=False,
        ignore_rules=True,
        timeout_seconds=300,
    )


def draft(workdir: Path, input_data: dict[str, Any], *, force: bool, fixture: str | None) -> dict[str, Any]:
    raw = input_data.get("raw_input_full")
    if not isinstance(raw, str) or not raw.strip():
        raise invalid("draft input requires raw_input_full")
    path = workdir / "brief.json"
    if path.exists() and not force:
        raise invalid("brief.json already exists; use revise or --force")
    prompt = (
        "Create a concise, decision-ready research brief from the user's complete request. "
        "Split only genuinely independent topics. Preserve constraints and prohibited actions. "
        "For each topic produce concrete research questions, source surfaces, and a stop condition. "
        "Return only the schema object.\n\nComplete request:\n"
        + raw
    )
    model_output = _fixture_or_model(fixture, prompt=prompt, workdir=workdir)
    brief = new_brief(raw, model_output.get("topics"))
    write_brief(path, brief)
    return {
        "brief_ref": "brief.json",
        "brief_path": public_path(path),
        "schema_version": BRIEF_SCHEMA,
        "revision": brief["revision"],
        "approval_status": brief["approval"]["status"],
        "content_sha256": brief_hash(brief),
    }


def revise(workdir: Path, input_data: dict[str, Any], *, fixture: str | None) -> dict[str, Any]:
    feedback = input_data.get("feedback")
    if not isinstance(feedback, str) or not feedback.strip():
        raise invalid("revise input requires feedback")
    path = workdir / "brief.json"
    current = load_brief(path)
    prompt = (
        "Revise the research brief using the user's feedback. Keep unaffected decisions stable, "
        "preserve the original request, and return the complete replacement topics array. "
        "Return only the schema object.\n\nCurrent brief:\n"
        + json.dumps({"topics": current["topics"]}, ensure_ascii=False, indent=2)
        + "\n\nFeedback:\n"
        + feedback
    )
    model_output = _fixture_or_model(fixture, prompt=prompt, workdir=workdir)
    updated = deepcopy(current)
    updated["topics"] = validate_topics(model_output.get("topics"))
    updated["revision"] = current["revision"] + 1
    updated["approval"] = {"status": "pending_confirmation", "content_sha256": None, "confirmed_at": None}
    write_brief(path, updated)
    return {
        "brief_ref": "brief.json",
        "brief_path": public_path(path),
        "revision": updated["revision"],
        "approval_status": "pending_confirmation",
        "content_sha256": brief_hash(updated),
    }


def confirm(workdir: Path, *, yes: bool) -> dict[str, Any]:
    if not yes:
        raise invalid("confirm requires --yes after explicit user approval")
    path = workdir / "brief.json"
    brief = load_brief(path)
    digest = brief_hash(brief)
    brief["approval"] = {"status": "confirmed", "content_sha256": digest, "confirmed_at": utc_now()}
    write_brief(path, brief)
    return {
        "brief_ref": "brief.json",
        "brief_path": public_path(path),
        "revision": brief["revision"],
        "approval_status": "confirmed",
        "content_sha256": digest,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = f"opening-{args.action}"
    try:
        workdir = workdir_path(args.workdir)
        if args.action == "draft":
            data = draft(workdir, read_json_input(args.input), force=args.force, fixture=args.fixture)
        elif args.action == "revise":
            data = revise(workdir, read_json_input(args.input), fixture=args.fixture)
        else:
            data = confirm(workdir, yes=args.yes)
        return emit(command, "ok", data)
    except Exception as exc:
        return fail(command, exc)


if __name__ == "__main__":
    raise SystemExit(main())
