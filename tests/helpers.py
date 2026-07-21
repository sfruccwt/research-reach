from __future__ import annotations

from pathlib import Path

from research_reach.contracts import brief_hash, new_brief, write_brief


def topics() -> list[dict]:
    return [{
        "topic_ref": "C1",
        "inquiry_shape": {"research_object": "Test subject", "operation_type": "comparison"},
        "research_goal": "Establish a traceable comparison.",
        "scope_boundary": {
            "in_scope": ["public evidence"],
            "out_of_scope": ["private data"],
            "action_in_scope": ["read public sources"],
            "action_out_of_scope": ["write to external systems"],
        },
        "output_contract": {"audience": "decision maker", "product_shape": "concise report"},
        "search_plan": {
            "questions": [
                {"question_ref": "q1", "question": "What does the primary source say?"},
                {"question_ref": "q2", "question": "What limitations are documented?"},
            ],
            "source_surfaces": ["primary", "web"],
            "stop_when": "Both questions have traceable evidence.",
        },
    }]


def confirmed_brief(workdir: Path) -> dict:
    brief = new_brief("Original request with all constraints.", topics())
    brief["approval"] = {
        "status": "confirmed",
        "content_sha256": brief_hash(brief),
        "confirmed_at": "2026-07-21T00:00:00.000Z",
    }
    write_brief(workdir / "brief.json", brief)
    return brief


def worker_result(*, questions: tuple[str, ...] = ("q1", "q2")) -> dict:
    evidence = []
    for index, question in enumerate(questions, 1):
        evidence.append({
            "question_refs": [question],
            "title": f"Source {index}",
            "url": f"https://example.com/source-{index}",
            "text": f"Evidence for {question}.",
            "evidence_kind": "fetched_content",
            "source_name": "Example",
            "retrieved_at": "2026-07-21T00:00:00Z",
        })
    return {"status": "ok", "evidence": evidence, "blocking_questions": [], "errors": []}
