#!/usr/bin/env python3
"""Small CLI for the EpiETL Epidemic Intelligence Data API."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = "https://epietl.com"
PATHS = {
    "health": "/api/health",
    "channels": "/api/channels",
    "events": "/api/risk/events",
    "reports": "/api/reports",
}
AUTH_REQUIRED_ENDPOINTS = {"events", "reports"}
COLLECTION_KEYS = {
    "channels": ("channels",),
    "events": ("items", "events"),
    "reports": ("items", "reports"),
}


def add_if_present(params: dict[str, str], key: str, value: object | None) -> None:
    if value is not None:
        params[key] = str(value)


def parse_extra_params(values: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise SystemExit(f"--param must be key=value, got: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--param key cannot be empty, got: {item}")
        params[key] = value
    return params


def build_url(endpoint: str, params: dict[str, str]) -> str:
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{PATHS[endpoint]}"
    return f"{url}?{query}" if query else url


def default_api_key() -> str | None:
    return os.environ.get("EPIETL_API_KEY") or os.environ.get("EPIETL_X_API_KEY")


def build_auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    key = api_key.strip()
    if not key:
        return {}
    if key.lower().startswith("bearer "):
        raw_key = key.split(None, 1)[1].strip()
        bearer = key
    else:
        raw_key = key
        bearer = f"Bearer {key}"
    return {
        "Authorization": bearer,
        "X-API-Key": raw_key,
    }


def apply_client_pagination(endpoint: str, payload: object, limit: int | None) -> object:
    """Trim collection payloads when the API returns more rows than requested."""
    if limit is None:
        return payload

    keys = COLLECTION_KEYS.get(endpoint)
    if keys is None or not isinstance(payload, dict):
        return payload

    key = next((candidate for candidate in keys if isinstance(payload.get(candidate), list)), None)
    if key is None:
        return payload

    items = payload.get(key)
    if not isinstance(items, list) or len(items) <= limit:
        return payload

    trimmed = dict(payload)
    kept_items = items[:limit]
    trimmed[key] = kept_items
    kept_ids = {item.get("id") for item in kept_items if isinstance(item, dict) and item.get("id")}
    if kept_ids:
        for group_key, group_value in payload.items():
            if group_key in {key, "client_pagination"} or not isinstance(group_value, dict):
                continue
            filtered_groups = {}
            should_replace = False
            for name, group_items in group_value.items():
                if not isinstance(group_items, list):
                    filtered_groups[name] = group_items
                    continue
                filtered = [
                    item
                    for item in group_items
                    if not isinstance(item, dict) or item.get("id") in kept_ids
                ]
                if filtered:
                    filtered_groups[name] = filtered
                should_replace = should_replace or len(filtered) != len(group_items)
            if should_replace:
                trimmed[group_key] = filtered_groups
    trimmed["client_pagination"] = {
        "applied": True,
        "collection": key,
        "limit": limit,
        "available_before_client_pagination": len(items),
        "returned": len(trimmed[key]),
    }
    return trimmed


def request_json(url: str, api_key: str | None, timeout: float) -> tuple[int, object]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "openclaw-epietl-api-skill/1.0",
    }
    headers.update(build_auth_headers(api_key))
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    try:
        return status, json.loads(body) if body else None
    except json.JSONDecodeError:
        return status, {"raw": body}


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the EpiETL API.")
    parser.add_argument("endpoint", choices=sorted(PATHS))
    parser.add_argument("--country")
    parser.add_argument("--organization")
    parser.add_argument("--pathogen")
    parser.add_argument("--severity")
    parser.add_argument("--risk-category", dest="risk_category")
    parser.add_argument("--period-from", dest="period_from")
    parser.add_argument("--period-to", dest="period_to")
    parser.add_argument("--keyword")
    parser.add_argument("--channel")
    parser.add_argument("--query", "--q", dest="query")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--offset", type=int)
    parser.add_argument("--param", action="append", default=[], help="Extra query parameter as key=value.")
    parser.add_argument("--api-key", help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--url-only", action="store_true", help="Print the request URL and exit.")
    args = parser.parse_args()

    if args.limit is not None and not 1 <= args.limit <= 200:
        raise SystemExit("--limit must be between 1 and 200")

    params = parse_extra_params(args.param)
    add_if_present(params, "country", args.country)
    add_if_present(params, "organization", args.organization)
    add_if_present(params, "pathogen", args.pathogen)
    add_if_present(params, "severity", args.severity)
    add_if_present(params, "risk_category", args.risk_category)
    add_if_present(params, "period_from", args.period_from)
    add_if_present(params, "period_to", args.period_to)
    add_if_present(params, "keyword", args.keyword or args.query)
    add_if_present(params, "channel", args.channel)
    add_if_present(params, "limit", args.limit)
    add_if_present(params, "offset", args.offset)

    url = build_url(args.endpoint, params)
    if args.url_only:
        print(url)
        return 0

    api_key = args.api_key or default_api_key()

    if args.endpoint in AUTH_REQUIRED_ENDPOINTS and not api_key:
        raise SystemExit(f"{args.endpoint} requires an API key. Set EPIETL_API_KEY or EPIETL_X_API_KEY.")

    status, payload = request_json(url, api_key, args.timeout)
    if 200 <= status < 300:
        payload = apply_client_pagination(args.endpoint, payload, args.limit)
    print(json.dumps({"status": status, "url": url, "data": payload}, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
