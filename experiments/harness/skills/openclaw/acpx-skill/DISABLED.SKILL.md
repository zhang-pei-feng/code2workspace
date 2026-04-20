# Archived Notes

旧版 `acpx-skill` 曾经桥接 `deepagents` 和一些过时入口。

当前版本已经切换为三路桥接：

- `benchmark_agent`
- `data_governance_agent`
- `deep_research_agent`

这份文件只保留作历史备注，不再作为当前操作说明。
3. For at least one agent, send a second prompt in the same mapped session and confirm continuity.

If prompt execution fails but session creation succeeds, inspect environment constraints before blaming the integration. In restricted sandboxes, ACP queue sockets under `/tmp` or stdio agent transport can be blocked.

## Constraints and caveats

- The included Deep Agents wrapper assumes the ACP demo lives at `${DEEPAGENTS_ACP_BASE_DIR}` or a relative fallback under the skill if `DEEPAGENTS_ACP_BASE_DIR` is not set.
- Other ACP agents must already exist in global `acpx` config or be added to the project `.acpxrc.json`.
- `acpx` session metadata normally lives under the current `HOME`-scoped `.acpx` directory.
- `acpx` queue sockets are created under `/tmp/acpx-*` based on `HOME`; this can fail in some sandboxes even when the setup is otherwise correct.
- The bundled launcher is for local execution, not for public network deployment.
