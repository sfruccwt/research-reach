# Research Reach

Research Reach is a three-stage, file-oriented research workflow for Codex. It keeps human review in Opening, isolates network retrieval in one Worker per topic, and isolates final synthesis in a networkless Worker.

```text
research-reach-opening   -> brief.json
research-reach-search    -> artifacts/search/<topic>/
research-reach-synthesis -> report.md
```

There is no cross-stage Run Store or lifecycle state machine. The confirmed brief and evidence files are the complete handoff contract.

## Install

```powershell
pwsh ./scripts/bootstrap.ps1
```

Optional model configuration lives at `~/.research-reach/models.json`; use `config.example/models.json` as the template.

## Example

```powershell
@{ raw_input_full = 'Compare the evidence for two implementation approaches.' } |
  ConvertTo-Json -Compress |
  research-reach-opening draft --workdir ./work/example --input -

research-reach-opening confirm --workdir ./work/example --yes
research-reach-search launch --workdir ./work/example
research-reach-synthesis run --workdir ./work/example
```

Confirmation must follow explicit user review. The three Companion Skills enforce that conversational gate.

## Test

```powershell
$env:PYTHONPATH = 'src'
python -m unittest discover -v
```

## Development Contracts

- `src/` is the source of truth. The console commands load the installed package, not the checkout; run `pwsh ./scripts/bootstrap.ps1` after source changes before live validation.
- Worker output schemas use the Codex strict subset of JSON Schema. For objects with `additionalProperties: false`, every property must also appear in `required`, including nullable properties. Unsupported keywords such as `uniqueItems` are rejected locally before a Worker starts; enforce those invariants in host validation instead.
- Public evidence uses absolute HTTP(S) URLs. A confirmed, de-identified local input uses a safe relative `artifact://` reference with `evidence_kind: metadata`. Network Workers must never receive a raw private file when an aggregate can answer the confirmed question.
- Codex executable resolution prefers a valid `RESEARCH_REACH_CODEX`, then the newest Windows desktop-app CLI copy, then `PATH`. A stale configured path is ignored.
- Worker failures expose only a parsed upstream error message and exit code. Raw stderr can contain prompts or evidence and must not enter the public CLI envelope.
