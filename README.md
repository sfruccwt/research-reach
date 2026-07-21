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
