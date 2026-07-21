---
name: research-reach-opening
description: Create, revise, and explicitly confirm a file-backed research brief for deliberate multi-source research, systematic comparison, evidence-chain work, or report-oriented investigation. Use for a new complex research request before any search begins. Do not use for quick fact lookup, one public URL, or a bounded single-platform request; route those to Agent Reach.
---

# Research Reach Opening

Use the installed `research-reach-opening` command. Keep stdout as JSON.

## Draft

1. Choose a dedicated local work directory, normally under the current workspace's ignored `work/` directory.
2. Preserve the user's complete request in `raw_input_full` and run:

   ```powershell
   @{ raw_input_full = 'complete request' } | ConvertTo-Json -Compress | research-reach-opening draft --workdir <path> --input -
   ```

3. Require the returned absolute `brief_path`. Show only a Markdown link to that file and ask the user to inspect it. Do not search yet.

## Revise Or Confirm

- For feedback, pass the complete feedback to `research-reach-opening revise --workdir <path> --input -`, show the updated file, and stop for review again.
- Only after the user explicitly confirms the linked revision, run `research-reach-opening confirm --workdir <path> --yes`.
- Never infer confirmation or edit `brief.json` directly. Any content edit invalidates confirmation.

After confirmation, stop unless the user also explicitly asks to execute the plan. Execution belongs to `$research-reach-search`.
