---
name: research-reach-search
description: Execute an already confirmed Research Reach brief by launching one isolated search Worker per topic and saving full evidence to local artifacts. Use when the user asks to run, continue, or retry a confirmed `brief.json`. Do not use for drafting the brief, synthesizing a report, or ordinary bounded lookup without a confirmed work package.
---

# Research Reach Search

Use the installed `research-reach-search` command. Keep stdout as JSON.

## Worker Guard

If `RESEARCH_REACH_WORKER_MODE=search`, never call `research-reach-search`, never launch another agent, and never synthesize. Use `$agent-reach` for public retrieval and its Web Access escalation only for sources that require a real browser. Return only the structured Worker output requested by the host prompt.

## Host Workflow

1. Require the work directory containing the explicitly confirmed `brief.json`.
2. Run one host command; it launches topics sequentially and isolates each Worker:

   ```powershell
   research-reach-search launch --workdir <path>
   ```

3. Treat `artifact_refs` as authoritative. Do not read or paste `evidence.jsonl` into the main conversation.
4. Report topic status, evidence counts, covered question refs, and links to returned artifact paths.
5. For `blocked`, ask only returned blocking questions. A retry reruns the affected topic and deduplicates evidence; it does not resume state.

Search never performs final synthesis. That belongs to `$research-reach-synthesis`.
