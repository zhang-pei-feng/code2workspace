# COVID 问题对照

- code2workspace: `10 passed / 2 runner_error`
- deepagents: `10 passed / 2 runner_error`

## 状态总表

| 题目 | code2workspace | deepagents |
| --- | --- | --- |
| `covid-monitoring-01-next-covid-flu-peak` | `passed` | `runner_error` |
| `covid-monitoring-02-spring-travel-covid-spread` | `passed` | `passed` |
| `covid-monitoring-03-guangzhou-event-covid-impact` | `passed` | `passed` |
| `covid-monitoring-04-clinical-vs-wastewater-trends` | `passed` | `passed` |
| `covid-monitoring-05-ba32-vs-xfg-severity` | `passed` | `runner_error` |
| `covid-monitoring-06-ba32-vaccine-trials` | `passed` | `passed` |
| `covid-monitoring-07-covid-flu-correlation-seasonality` | `runner_error` | `passed` |
| `covid-monitoring-08-may-mainland-dominant-lineage` | `runner_error` | `passed` |
| `covid-monitoring-09-fastest-growing-sublineage` | `passed` | `passed` |
| `covid-monitoring-10-s-protein-escape-sites` | `passed` | `passed` |
| `covid-monitoring-11-us-trend-deaths-ed-positivity` | `passed` | `passed` |
| `covid-monitoring-12-covid-flu-rsv-overview` | `passed` | `passed` |

## 代表性差异

### `covid-monitoring-01-next-covid-flu-peak`

- code2workspace: `passed`
  - 给出了中国官方监测基础上的时间窗判断，答案完整。
- deepagents: `runner_error`
  - 直接报 `InternalServerError`，未形成有效回答。

### `covid-monitoring-05-ba32-vs-xfg-severity`

- code2workspace: `passed`
  - 能给出“暂无证据显示哪一支明确提高重症率”的保守结论。
- deepagents: `runner_error`
  - 报错退出，未形成有效回答。

### `covid-monitoring-07-covid-flu-correlation-seasonality`

- code2workspace: `runner_error`
  - 在相关性/周期性这个更长链路问题上超时。
- deepagents: `passed`
  - 给出了更定量的周期性结论，包括 CDC 周期分析和季节性解释。

### `covid-monitoring-08-may-mainland-dominant-lineage`

- code2workspace: `runner_error`
  - 后端内部错误，未完成回答。
- deepagents: `passed`
  - 明确回答主导株是 `NB.1.8.1`，答案更直接。

## 当前结论

- 两者总通过数打平，都是 `10/12`。
- `code2workspace` 在前两类问题上更稳：
  - 下一波高峰时间判断
  - BA.3.2 vs XFG 重症率判断
- `deepagents` 在后两类问题上更稳：
  - 新冠/流感相关性与季节性
  - 今年 5 月中国大陆主导株判断
- 若只看这 12 题，目前更像是**失败分布不同，而不是某一方全面更强**。
