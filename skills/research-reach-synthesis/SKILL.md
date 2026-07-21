---
name: research-reach-synthesis
description: Generate a final traceable report from an explicitly confirmed Research Reach brief and existing search artifacts by using an isolated networkless synthesis Worker. Use when search is finished or the user asks to synthesize an existing work package. Do not use to perform new searches or repair missing evidence with network calls.
---

# Research Reach Synthesis

Use the installed `research-reach-synthesis` command. Keep stdout as JSON.

## Worker Guard

If `RESEARCH_REACH_WORKER_MODE=synthesis`, never call a Research Reach CLI, launch another agent, or access the network. Use only the brief and evidence supplied by the host prompt and return the requested structured report object.

## Host Workflow

1. Require a confirmed `brief.json` and its matching search manifests.
2. Run:

   ```powershell
   research-reach-synthesis run --workdir <path>
   ```

3. Require `report_path`. Return a Markdown link plus the compact assessment and source count.
4. Do not load full evidence into the main conversation. Read a specific artifact only to diagnose an explicit validation error.
5. Never perform fallback search from this stage. Missing evidence must remain visible as `partial` or `insufficient`.
