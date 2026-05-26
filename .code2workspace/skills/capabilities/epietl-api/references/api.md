# EpiETL API Reference

Base URL: `https://epietl.com`

## Authentication

Authenticated endpoints accept either header:

```http
Authorization: Bearer epietl_<token>
X-API-Key: epietl_<token>
```

Use `EPIETL_API_KEY` with the bundled helper. Do not store API keys in this
repository.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---:|---|
| `GET` | `/api/reports` | Yes | Search surveillance reports. |
| `GET` | `/api/risk/events` | Yes | Search AI-extracted pathogen risk events. |
| `GET` | `/api/channels` | No | List monitored source channels. |
| `GET` | `/api/health` | No | Health check. |

Authenticated `reports` and `events` endpoints return:

```json
{
  "total": 739,
  "limit": 50,
  "offset": 0,
  "items": []
}
```

## `/api/reports`

Parameters:

| Param | Type | Description |
|---|---|---|
| `country` | string | Country / region name, fuzzy match. |
| `organization` | string | Source organization name, fuzzy match. |
| `period_from` | `YYYY-MM-DD` | `publish_date >= period_from`. |
| `period_to` | `YYYY-MM-DD` | `publish_date <= period_to`. |
| `keyword` | string | Title / content keyword, fuzzy match. |
| `limit` | int, 1-200 | Page size. |
| `offset` | int | Pagination offset. |

Example:

```bash
curl -H "Authorization: Bearer $EPIETL_API_KEY" \
  "https://epietl.com/api/reports?country=China&limit=5"
```

## `/api/risk/events`

Parameters:

| Param | Type | Description |
|---|---|---|
| `country` | string | Country name, fuzzy match. |
| `severity` | `critical`, `high`, `medium`, `low` | Risk level. |
| `risk_category` | `respiratory`, `vector_borne`, `other` | Risk category. |
| `pathogen` | string | Pathogen name, fuzzy match. |
| `period_from` | `YYYY-MM-DD` | `period_start >= period_from`. |
| `period_to` | `YYYY-MM-DD` | `period_end <= period_to`. |
| `limit` | int, 1-200 | Page size. |
| `offset` | int | Pagination offset. |

Example:

```bash
curl -H "Authorization: Bearer $EPIETL_API_KEY" \
  "https://epietl.com/api/risk/events?severity=critical&pathogen=cholera"
```

## `/api/channels`

Public channel catalogue:

```bash
curl "https://epietl.com/api/channels"
```

Use this endpoint to discover monitored `channel_id`, organization, country,
source type, base URL, and last sync metadata.

## Errors

| Code | Meaning | What to do |
|---|---|---|
| `400` | Bad query | Show the message and retry with fixed params. |
| `401` | Missing / invalid key | Ask the user for a valid `epietl_<token>`. |
| `429` | Rate-limited | Back off, then retry. |
| `5xx` | Server error | Retry once; otherwise surface the failure. |

## Suggested Citation

Data sourced from EpiETL (`https://epietl.com`), developed and maintained by
Greater Bay Area Center for Bioinformation (GBACB). Original surveillance data
published by respective national and international public health agencies; see
individual report source URLs for details.
