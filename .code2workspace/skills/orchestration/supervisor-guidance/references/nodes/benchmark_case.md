# Benchmark Case Node Guidance

- Prefer the concrete execution context already prepared by the registration node.
- Read the latest registration/readiness artifact first and reuse its recommended launch command when available.
- You are responsible for the whole per-operator case: inspect the case manifest, choose the execution path, run it, repair one bounded blocker if needed, verify outputs, run or produce analysis artifacts, and return a structured result.
- If an execution-contract artifact exists for this case, treat it as the strongest starting plan, but stay in control of verification and repair instead of assuming the command succeeded.
- If register artifacts already name the shared dataset, resolved inputs, expected outputs, and helper command, do not keep searching for alternatives.
- You may use the benchmark helper as a tool command when it matches the case, but do not rely on supervisor to run it for you. Common helper command shape:
  `python3 .code2workspace/skills/orchestration/benchmark-workflow-orchestrator/scripts/benchmark_workflow.py run-repo-native --repo <repo> --run-dir <run_dir>`
- When you call the `execute` tool, keep `timeout` at or below `3600` seconds. If a helper example, copied command, or inferred plan suggests a longer timeout, shorten it before calling the tool.
- If the repo-native helper path is absent or fails for a concrete reason, try the staged WDL path when `workflow.wdl` and `inputs.json` are present.
- Execute one concrete case path first, then inspect the resulting status and output artifacts.
- If the first execution fails because of a small staged-case issue, make a bounded repair in the case directory and retry once before returning failure.
- Do not spend time probing generic tool metadata once a runnable launch command is already known.
- After the command exits, inspect only the expected outputs declared by the case manifest or result manifest.
- Do not read full FASTA, BAM, VCF, or large log files after completion.
- Use only lightweight checks such as file existence, file size, directory listing, and log tail when needed.
- Write or preserve a small result-manifest artifact that records exact output paths, exit code, and lightweight file checks.
- Ensure `analysis.json` and `analysis.md` exist when the case produced outputs. If a family-specific extractor is available, run it; otherwise write a conservative analysis with artifact paths, checksums when available, and an empty or clearly limited metrics object.
- As soon as those artifacts or a concrete failure log exist, return the structured JSON result immediately.
