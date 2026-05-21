# Benchmark Case Node Guidance

- Prefer the concrete execution context already prepared by the registration node.
- Read the latest registration/readiness artifact first and reuse its staged WDL, staged `inputs.json`, runtime image, and expected outputs when available.
- You are responsible for the whole per-operator case: inspect the case manifest, choose the execution path, run it, repair one bounded blocker if needed, verify outputs, run or produce analysis artifacts, and return a structured result.
- If an execution-contract artifact exists for this case, treat it as the strongest starting plan, but stay in control of verification and repair instead of assuming the command succeeded.
- If register artifacts already name the shared dataset, resolved inputs, staged WDL, and expected outputs, do not keep searching for alternatives.
- Treat `dataset_manifest.json` and the staged `wdl/inputs.json` as the source of truth for this case's assigned dataset.
- In strict shared-dataset mode, do not switch to another local case input bundle just because it looks convenient; if the staged inputs still point at a different dataset than the shared dataset declared by registration, fix that mismatch before running the tool.
- In exploratory mode, the assigned dataset may differ across tools. If the assigned input bundle fails and the tool can plausibly consume another local FASTA/FASTQ bundle, you may make one bounded attempt to adapt the staged inputs, but record the actual input paths and do not claim same-dataset fairness.
- When you call the `execute` tool, keep `timeout` at or below `3600` seconds. If a helper example, copied command, or inferred plan suggests a longer timeout, shorten it before calling the tool.
- Prefer this execution order:
  1. inspect `manifest.json`, `execution_ready.json`, `dataset_manifest.json`, staged `wdl/*.wdl`, and staged `wdl/inputs.json`
  2. if a staged WDL and staged `inputs.json` exist, run that concrete workflow directly with `miniwdl run -i <inputs.json> -d <case_run_dir> <workflow.wdl>`
  3. only if the staged workflow path is truly unusable, look for a concrete repo-native command already recorded in the case artifacts
- Execute one concrete case path first, then inspect the resulting status and output artifacts.
- If the first execution fails because of a small staged-case issue, make a bounded repair in the case directory and retry once before returning failure.
- Do not spend time probing generic tool metadata once a runnable launch command is already known.
- After the command exits, inspect only the expected outputs declared by the case manifest or result manifest.
- Do not read full FASTA, BAM, VCF, or large log files after completion.
- Use only lightweight checks such as file existence, file size, directory listing, and log tail when needed.
- Write or preserve a small result-manifest artifact that records exact output paths, exit code, and lightweight file checks.
- Ensure `analysis.json` and `analysis.md` exist before you return. If you cannot derive trustworthy family-specific metrics, write a conservative analysis with artifact paths, checksums when available, `real_contigs_fasta` or equivalent output-presence flags, and an empty or clearly limited metrics object.
- As soon as those artifacts or a concrete failure log exist, return the structured JSON result immediately.
- If you discover the staged case violates an explicitly required shared benchmark dataset, return `blocked` or repair the staged inputs first; do not report a comparison result from mismatched datasets.
- If datasets differ because registration chose exploratory mode, continue the case when it is otherwise runnable and make the dataset boundary explicit in `analysis.json` / `analysis.md`.
