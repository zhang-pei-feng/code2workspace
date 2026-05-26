---
name: epietl-api
description: Query the EpiETL surveillance database for authenticated surveillance reports and AI-extracted risk events, and use the public channel catalogue for source/channel discovery. Use for EpiETL, epidemic intelligence, infectious-disease surveillance reports, pathogen risk events, public-health source catalog/source URL/source type questions, and structured respiratory/COVID/flu source discovery.
---

# EpiETL - Database Query API

You are an AI agent with access to the **EpiETL** surveillance database
through two HTTP endpoints. This skill is **query-only**: search reports
and AI-extracted risk events. It does not aggregate, summarize, or reason
on its own - that is your job once you have the rows.

Data comes from official surveillance channels (WHO, ECDC, US CDC,
China CDC, Africa CDC, PAHO, national CDCs, ...) and is refreshed daily.

---

## Local helper

Prefer the bundled helper from the repository root instead of hand-writing
`curl`:

```bash
python3 skills/capabilities/epietl-api/scripts/epietl_api.py health
python3 skills/capabilities/epietl-api/scripts/epietl_api.py channels --limit 20
python3 skills/capabilities/epietl-api/scripts/epietl_api.py reports --country China --limit 5
python3 skills/capabilities/epietl-api/scripts/epietl_api.py events --severity critical --pathogen cholera --limit 10
```

For authenticated endpoints, set `EPIETL_API_KEY` or `EPIETL_X_API_KEY` in
the environment before running the helper. The helper sends both
`Authorization: Bearer <key>` and `X-API-Key: <key>` when a key is
available. It also applies client-side trimming when a collection endpoint
returns more rows than requested.

---

## When to use this skill

Trigger on user questions such as:

- _"Find recent surveillance reports about H5N1 in Cambodia."_
- _"What critical risk events are active right now?"_
- _"Show ECDC respiratory reports from the last 30 days."_
- _"Compare dengue activity in Brazil vs. Argentina this month."_
- _"Which public-health source channels or structured data sources does
  EpiETL know about?"_

Do **not** use this skill for general medical advice, individual diagnosis,
or non-infectious-disease questions.

---

## Base URL & authentication

```text
Base URL:  https://epietl.com
Header:    Authorization: Bearer epietl_<token>
           (X-API-Key: epietl_<token> is also accepted)
Get a key: https://epietl.com/?tab=api  ->  API Keys
```

If the user has not provided a key and the task needs `reports` or
`events`, ask for one before calling those endpoints. The public
`channels` and `health` endpoints can be used without a key for source
catalogue discovery and connectivity checks.

---

## Endpoints

Authenticated `reports` and `events` endpoints return the same envelope:

```json
{
  "total": 739,
  "limit": 50,
  "offset": 0,
  "items": [ /* rows */ ]
}
```

### 1. `GET /api/reports` - surveillance reports

Search the report catalogue. Results are paginated, sorted by `synced_at`
descending.

| Param | Type | Default | Description |
|---|---|---|---|
| `country` | string | - | Country / region name (fuzzy match) |
| `organization` | string | - | Source organization name (fuzzy match) |
| `period_from` | `YYYY-MM-DD` | - | `publish_date >= period_from` |
| `period_to` | `YYYY-MM-DD` | - | `publish_date <= period_to` |
| `keyword` | string | - | Title / content keyword (fuzzy match) |
| `limit` | int (1-200) | 50 | Page size |
| `offset` | int | 0 | Pagination offset |

```bash
curl -H "Authorization: Bearer YOUR_KEY" \
  "https://epietl.com/api/reports?country=China&limit=5"
```

Each row in `items`:

```json
{
  "report_id": "2caaf69a17e4d02e",
  "channel_id": "tw_cdc_covid",
  "title": "COVID-19 Epidemic Report",
  "organization": "Taiwan Centers for Disease Control",
  "country": "China (Taiwan)",
  "publish_date": "2026-03-30",
  "epidemiological_week": 12,
  "period_start": "2026-03-24",
  "period_end": "2026-03-30",
  "source_url": "https://...",
  "pdf_path": "pdf/tw_cdc_covid/.../report.pdf",
  "char_count": 2717,
  "extracted_at": "2026-04-05T21:09:09",
  "synced_at": "2026-04-05T21:47:00"
}
```

### 2. `GET /api/risk/events` - AI-extracted risk events

Search structured risk events distilled from the reports above. Ordered
by `period_end` desc, then severity priority.

| Param | Type | Default | Description |
|---|---|---|---|
| `country` | string | - | Country name (fuzzy) |
| `severity` | `critical` \| `high` \| `medium` \| `low` | - | Risk level |
| `risk_category` | `respiratory` \| `vector_borne` \| `other` | - | Category |
| `pathogen` | string | - | Pathogen name (fuzzy) |
| `period_from` | `YYYY-MM-DD` | - | `period_start >= period_from` |
| `period_to` | `YYYY-MM-DD` | - | `period_end <= period_to` |
| `limit` | int (1-200) | 50 | Page size |
| `offset` | int | 0 | Pagination offset |

```bash
curl -H "Authorization: Bearer YOUR_KEY" \
  "https://epietl.com/api/risk/events?severity=critical&pathogen=cholera"
```

Each row in `items`:

```json
{
  "title": "Cholera outbreak across multiple African countries",
  "severity": "critical",
  "category": "other",
  "pathogen": "Vibrio cholerae",
  "summary": "Ongoing cholera outbreak with high case counts...",
  "country": "Dem. Rep. Congo",
  "epi_week": "2026-W07",
  "period_start": "2026-02-08",
  "period_end": "2026-02-15",
  "regions": ["Dem. Rep. Congo", "Mozambique", "Angola"],
  "source_url": "https://...",
  "source_org": "Africa CDC"
}
```

### 3. `GET /api/channels` - public channel catalogue

This public endpoint returns monitored sources with `channel_id`,
organization, country, source type, base URL, and sync metadata. Use it
when the user asks about source catalogues, source URLs, source types, or
which organization strings to use in report queries.

```bash
python3 skills/capabilities/epietl-api/scripts/epietl_api.py channels --limit 20
```

---

## Query cookbook

Map natural-language asks to one or two calls. Substitute real dates
(today minus N days) where you see `YYYY-MM-DD`.

- **"What surveillance reports has China published in the last 30 days?"**
  `GET /api/reports?country=China&period_from=YYYY-MM-DD&limit=50`

- **"Any critical-severity risk events worldwide right now?"**
  `GET /api/risk/events?severity=critical&limit=50`

- **"Recent dengue activity in Brazil?"**
  `GET /api/risk/events?country=Brazil&pathogen=dengue&period_from=YYYY-MM-DD`

- **"Find original reports mentioning H5N1."**
  `GET /api/reports?keyword=H5N1&limit=10`

- **"What has ECDC published about respiratory illness?"**
  `GET /api/reports?organization=ECDC&keyword=respiratory&limit=20`

- **"Vector-borne risks in Latin America."**
  Iterate per country, e.g.
  `GET /api/risk/events?country=Brazil&risk_category=vector_borne` and combine.

- **"Pull every match, not just the first page."**
  Loop with `offset += limit` until `len(items) < limit`. Hard cap of 200 per page.

- **"Just give me titles and dates, no PDF text."**
  Default response already excludes full markdown - no extra parameter
  needed, and `char_count` tells you how big the body would be.

When the user asks for an analysis ("compare X and Y", "what's new this
week", "is there an outbreak in Z"), make **2-4 targeted calls** and
synthesize. Do not try to one-shot it with a single broad query.

---

## Errors

| Code | Meaning | What to do |
|---|---|---|
| `400` | Bad query (e.g. malformed date) | Show the message and retry with fixed params |
| `401` | Missing / invalid key | Ask the user for a valid `epietl_<token>` |
| `429` | Rate-limited (default 100 req/min per key) | Back off, then retry |
| `5xx` | Server error | Retry once; otherwise surface the failure |

---

## Citation rule

Every factual claim in your answer **must** cite the originating report
through `items[].source_url` and `items[].source_org` (for events) or
`items[].source_url` and `items[].organization` (for reports). Do not
invent figures, dates, or source institutions.

**Per-claim citation** (inline, for each fact you quote):

> Malawi reported a 204% increase in cholera cases in early April
> ([Africa CDC, 2026-04-09](https://example.org/africa-cdc-report)).

**Overall attribution** (include verbatim whenever you produce a
report, summary, or research artifact built on this data):

> Data sourced from EpiETL (https://epietl.com), developed and
> maintained by Greater Bay Area Center for Bioinformation (GBACB).
> Original surveillance data published by respective national and
> international public health agencies; see individual report source
> URLs for details.

---

## More

- **Interactive docs + key management:**
  [https://epietl.com/?tab=api](https://epietl.com/?tab=api) - see every
  parameter, copy-pasteable curl, and create / revoke keys there.
- **Channel catalogue (public, no key required):**
  `GET https://epietl.com/api/channels` returns every monitored source
  with its `channel_id`, organization, country, and last sync time. Use
  it to learn which `organization` strings will match.
- **Honesty:** data is AI-extracted from public surveillance reports;
  always verify critical claims against `source_url`. Do not claim
  access to private datasets. Cite both **EpiETL** and the original
  agency in research contexts.
