#!/usr/bin/env python3
import argparse
from collections import Counter
import json
import re
from html import unescape
from urllib.parse import urljoin

import requests

TIMEOUT_SECONDS = 20
MAX_LINKS = 5
USER_AGENT = "OpenClaw respiratory-disease-data-fetcher/1.0"
WHO_CASE_ENDPOINT = "https://xmart-api-public.who.int/DATA_/RELAY_COVID_REPORT"
WHO_GLOBAL_M49 = "001"
CDC_BASE_URL = "https://www.cdc.gov"
CDC_POSITIVITY_CONFIG = "/respiratory-viruses/modules/test-in-percent-test-positivity-in-usa.json"
CDC_ARI_CONFIG = "/respiratory-viruses/modules/respiratory-virus-activity/ARI_Map_Viz.json"

WHO_CASE_INDICATORS = {
    "latest_reported_date": ("JVAJ4BACOVID_CASES_LAST_REPORTED", "VALUE_LABEL"),
    "latest_reported_date_last_7_days": ("JVAJ4BACOVID_CASES_LAST_REPORTED_LAST7DAYS", "VALUE_LABEL"),
    "latest_reported_date_last_28_days": ("JVAJ4BACOVID_CASES_LAST_REPORTED_LAST28DAYS", "VALUE_LABEL"),
    "reported_cases_latest_period": ("JVAJ4BACOVID_CASES_NUM_REPORTED", "VALUE_NUMERIC"),
    "reported_cases_last_7_days": ("JVAJ4BACOVID_CASES_NUM_REPORTED_LAST7DAYS", "VALUE_NUMERIC"),
    "reported_cases_last_28_days": ("JVAJ4BACOVID_CASES_NUM_REPORTED_LAST28DAYS", "VALUE_NUMERIC"),
}

SOURCES = {
    "who_cases": {
        "label": "WHO COVID-19 Cases Dashboard",
        "url": "https://data.who.int/dashboards/covid19/cases",
    },
    "us_cdc_trends": {
        "label": "US CDC Respiratory Illness Activity and Test Positivity",
        "url": "https://www.cdc.gov/respiratory-viruses/data/activity-levels.html",
    },
    "china_cdc": {
        "label": "China CDC Respiratory Disease Updates",
        "url": "https://www.chinacdc.cn/jksj/xgbdyq/",
    },
    "who_africa_updates": {
        "label": "WHO Africa Outbreak Updates",
        "url": "https://www.afro.who.int/health-topics/disease-outbreaks/outbreaks-and-other-emergencies-updates",
    },
    "who_variants": {
        "label": "WHO COVID-19 Variants Dashboard",
        "url": "https://data.who.int/dashboards/covid19/variants",
    },
}


def build_session():
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def clean_text(raw):
    return re.sub(r"\s+", " ", unescape(raw or "")).strip()


def parse_int(raw):
    if raw is None:
        return None
    text = str(raw).replace(",", "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_float(raw):
    if raw is None:
        return None
    text = str(raw).replace(",", "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_percent_series(raw):
    if not raw:
        return []
    values = []
    for item in re.findall(r"\d+(?:\.\d+)?\s*%", raw):
        value = parse_float(item)
        if value is not None:
            values.append(value)
    return values


def fetch_json(session, url, *, params=None):
    response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def extract_title(html):
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    return clean_text(match.group(1)) if match else ""


def extract_description(html):
    patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return clean_text(match.group(1))
    return ""


def extract_links(html, limit=MAX_LINKS):
    links = []
    seen = set()
    for href, text in re.findall(r'<a[^>]+href=["\'](.*?)["\'][^>]*>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL):
        href = clean_text(href)
        text = clean_text(re.sub(r"<[^>]+>", " ", text))
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        key = (href, text)
        if key in seen:
            continue
        seen.add(key)
        links.append({"text": text, "href": href})
        if len(links) >= limit:
            break
    return links


def strip_tags(html):
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</h\d\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return clean_text(text)


def extract_china_cdc_monthly_reports(html):
    reports = []
    pattern = re.compile(
        r'<a href=["\'](?P<href>[^"\']*t\d+_\d+\.html)["\'][^>]*>'
        r"(?P<body>.*?)</a>\s*<p\s+class=[\"']zy[\"']>\s*(?P<summary>.*?)</p>",
        flags=re.DOTALL,
    )
    for match in pattern.finditer(html):
        body = match.group("body")
        date_match = re.search(r"<span[^>]*>(.*?)</span>", body, flags=re.DOTALL)
        title_html = re.sub(r"<span[^>]*>.*?</span>", "", body, flags=re.DOTALL)
        title = strip_tags(title_html)
        if "全国新型冠状病毒感染疫情情况" not in title:
            continue
        month_match = re.search(r"（([^）]+)）", title)
        reports.append(
            {
                "title": title,
                "month": clean_text(month_match.group(1)) if month_match else "",
                "published_at": clean_text(date_match.group(1)) if date_match else "",
                "href": match.group("href"),
                "summary": strip_tags(match.group("summary")),
            }
        )
    return reports


def fetch_text(session, url):
    response = session.get(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text or ""


def search_first(pattern, text):
    match = re.search(pattern, text, flags=re.DOTALL)
    return clean_text(match.group(1)) if match else None


def search_all(pattern, text):
    return [clean_text(item) for item in re.findall(pattern, text, flags=re.DOTALL)]


def extract_china_cdc_structured_indicators(detail_text):
    indicators = {}
    period = search_first(r"(20\d{2}年\d{1,2}月\d{1,2}日-\d{1,2}月\d{1,2}日)", detail_text)
    if period:
        indicators["period"] = period

    fever_summary = search_first(r"发热门诊（诊室）诊疗情况\s*(.*?)\s*(?:见)?图1", detail_text)
    if fever_summary:
        indicators["fever_clinic_summary"] = fever_summary
        fever_values = [parse_float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*万人次", fever_summary)]
        indicators["fever_clinic_visits_10k_series"] = [value for value in fever_values if value is not None]

    confirmed = parse_int(search_first(r"新增确诊病例\s*([0-9,]+)\s*例", detail_text))
    if confirmed is not None:
        indicators["reported_confirmed_cases"] = confirmed

    severe = parse_int(search_first(r"重症病例\s*([0-9,]+)\s*例", detail_text))
    if severe is not None:
        indicators["reported_severe_cases"] = severe

    deaths = parse_int(search_first(r"死亡病例\s*([0-9,]+)\s*例", detail_text))
    if deaths is not None:
        indicators["reported_deaths"] = deaths

    ili_share = parse_percent_series(
        search_first(r"流感样病例占门（急）诊就诊人数比例.*?分别为\s*([0-9.%、，,\s]+)", detail_text)
    )
    if ili_share:
        indicators["ili_visit_share_percent_series"] = ili_share

    covid_positivity = parse_percent_series(
        search_first(r"新冠病毒阳性率.*?分别为\s*([0-9.%、，,\s]+)", detail_text)
    )
    if covid_positivity:
        indicators["covid_positivity_percent_series"] = covid_positivity

    sequences = parse_int(search_first(r"共报送\s*([0-9,]+)\s*例本土病例新冠病毒基因组有效序列", detail_text))
    if sequences is not None:
        indicators["local_genome_sequences"] = sequences

    main_variant = search_first(r"主要流行株为([^。]+)", detail_text)
    if main_variant:
        indicators["dominant_variant"] = main_variant

    variant_share = parse_percent_series(search_first(r"占比分别为\s*([0-9.%、，,\s]+)", detail_text))
    if variant_share:
        indicators["dominant_variant_share_percent_series"] = variant_share

    lineages = search_all(r"(?<![A-Za-z0-9.])([A-Z]{1,4}(?:\.[A-Z0-9]+)+)(?![A-Za-z0-9.])", detail_text)
    if lineages:
        seen = []
        for item in lineages:
            if item not in seen:
                seen.append(item)
        indicators["mentioned_lineages"] = seen[:10]
    return indicators


def enrich_china_cdc_result(session, result, html):
    reports = extract_china_cdc_monthly_reports(html)
    if reports:
        result["monthly_reports"] = reports[:6]
    if not reports:
        return result

    latest = reports[0].copy()
    latest["url"] = urljoin(result["final_url"], latest.pop("href"))

    try:
        detail_html = fetch_text(session, latest["url"])
        detail_text = strip_tags(detail_html)

        indicators = extract_china_cdc_structured_indicators(detail_text)
        latest["structured_indicators"] = indicators
        for old_key, new_key in {
            "period": "period",
            "confirmed_cases": "reported_confirmed_cases",
            "severe_cases": "reported_severe_cases",
            "death_cases": "reported_deaths",
            "main_variant": "dominant_variant",
            "mentioned_lineages": "mentioned_lineages",
        }.items():
            if new_key in indicators:
                latest[old_key] = indicators[new_key]
        if "covid_positivity_percent_series" in indicators:
            latest["covid_positivity_percent_series"] = indicators["covid_positivity_percent_series"]
        if "dominant_variant_share_percent_series" in indicators:
            latest["variant_share_percent_series"] = indicators["dominant_variant_share_percent_series"]
    except requests.RequestException as exc:
        latest["detail_error"] = str(exc)

    result["latest_report"] = latest
    return result


def fetch_who_case_metrics(session, geo_code=WHO_GLOBAL_M49):
    metrics = {}
    for metric_name, (indicator, value_key) in WHO_CASE_INDICATORS.items():
        params = {
            "$top": "1",
            "$filter": f"IND_ID eq '{indicator}' and DIM_GEO_CODE_M49 eq '{geo_code}'",
            "$select": "IND_ID,DIM_TIME,DIM_GEO_CODE_M49,VALUE_NUMERIC,VALUE_LABEL",
            "$orderBy": "DIM_TIME desc",
        }
        payload = fetch_json(session, WHO_CASE_ENDPOINT, params=params)
        row = (payload.get("value") or [{}])[0] if isinstance(payload, dict) else {}
        value = row.get(value_key)
        if value_key == "VALUE_NUMERIC":
            value = parse_int(value)
        metrics[metric_name] = {
            "indicator_id": indicator,
            "dim_time": row.get("DIM_TIME"),
            "value": value,
        }
        if value_key == "VALUE_NUMERIC":
            metrics[metric_name]["unit"] = "reported cases"
    return {
        "endpoint": WHO_CASE_ENDPOINT,
        "geo_code_m49": geo_code,
        "geo_label": "World",
        "metrics": metrics,
    }


def enrich_who_cases_result(session, result):
    try:
        result["structured_metrics"] = fetch_who_case_metrics(session)
    except requests.RequestException as exc:
        result.setdefault("data_quality_notes", []).append(f"WHO structured case metrics failed: {exc}")
    except (ValueError, KeyError, IndexError) as exc:
        result.setdefault("data_quality_notes", []).append(f"WHO structured case metrics parse failed: {exc}")
    return result


def cdc_json_url(path_or_url):
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    return urljoin(CDC_BASE_URL, path_or_url)


def latest_by_group(rows, *, group_key, date_key):
    latest = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        group = row.get(group_key)
        date = row.get(date_key)
        if not group or not date:
            continue
        if group not in latest or date > latest[group].get(date_key, ""):
            latest[group] = row
    return latest


def fetch_cdc_data_rows(session, config):
    rows = config.get("data")
    if isinstance(rows, list):
        return rows, None
    data_url = config.get("dataUrl") or config.get("runtimeDataUrl")
    if not data_url:
        return [], None
    if "wcms-wp.cdc.gov" in data_url and config.get("dataUrl"):
        data_url = config["dataUrl"]
    resolved = cdc_json_url(data_url)
    payload = fetch_json(session, resolved)
    return payload if isinstance(payload, list) else [], resolved


def enrich_us_cdc_result(session, result, html):
    config_urls = re.findall(r'data-config-url=["\']([^"\']+\.json)["\']', html)
    if config_urls:
        result["module_configs"] = [cdc_json_url(url) for url in config_urls]

    try:
        positivity_config = fetch_json(session, cdc_json_url(CDC_POSITIVITY_CONFIG))
        rows, data_url = fetch_cdc_data_rows(session, positivity_config)
        latest = latest_by_group(rows, group_key="pathogen", date_key="week_end")
        result["percent_test_positivity"] = {
            "config_url": cdc_json_url(CDC_POSITIVITY_CONFIG),
            "data_url": data_url or cdc_json_url(positivity_config.get("dataUrl", "")),
            "latest_by_pathogen": {
                pathogen: {
                    "week_end": row.get("week_end"),
                    "percent_test_positivity": parse_float(row.get("percent_test_positivity")),
                }
                for pathogen, row in sorted(latest.items())
            },
            "recent_rows": [
                {
                    "week_end": row.get("week_end"),
                    "pathogen": row.get("pathogen"),
                    "percent_test_positivity": parse_float(row.get("percent_test_positivity")),
                }
                for row in sorted(rows, key=lambda item: item.get("week_end", ""))[-9:]
            ],
        }
    except requests.RequestException as exc:
        result.setdefault("data_quality_notes", []).append(f"CDC percent positivity fetch failed: {exc}")
    except (ValueError, KeyError, TypeError) as exc:
        result.setdefault("data_quality_notes", []).append(f"CDC percent positivity parse failed: {exc}")

    try:
        ari_config = fetch_json(session, cdc_json_url(CDC_ARI_CONFIG))
        rows, data_url = fetch_cdc_data_rows(session, ari_config)
        latest_week = max((row.get("week_end", "") for row in rows if isinstance(row, dict)), default="")
        latest_rows = [row for row in rows if isinstance(row, dict) and row.get("week_end") == latest_week]
        counts = Counter(row.get("label") for row in latest_rows if row.get("label"))
        result["acute_respiratory_illness_activity"] = {
            "config_url": cdc_json_url(CDC_ARI_CONFIG),
            "data_url": data_url,
            "week_end": latest_week,
            "level_counts": dict(sorted(counts.items())),
            "state_levels": [
                {"geography": row.get("geography"), "level": row.get("label")}
                for row in latest_rows
                if row.get("geography") and row.get("label")
            ],
        }
    except requests.RequestException as exc:
        result.setdefault("data_quality_notes", []).append(f"CDC ARI activity fetch failed: {exc}")
    except (ValueError, KeyError, TypeError) as exc:
        result.setdefault("data_quality_notes", []).append(f"CDC ARI activity parse failed: {exc}")

    return result


def fetch_page(session, name, config):
    result = {
        "source": name,
        "label": config["label"],
        "url": config["url"],
    }
    try:
        response = session.get(config["url"], timeout=TIMEOUT_SECONDS)
        result["status_code"] = response.status_code
        result["final_url"] = response.url
        result["content_type"] = response.headers.get("content-type")

        if not response.ok:
            result["error"] = f"HTTP {response.status_code}"
            return result

        text = response.text or ""
        result["title"] = extract_title(text)
        description = extract_description(text)
        if description:
            result["description"] = description
        links = extract_links(text)
        if links:
            result["links"] = links
        if name == "who_cases":
            enrich_who_cases_result(session, result)
        if name == "us_cdc_trends":
            enrich_us_cdc_result(session, result, text)
        if name == "china_cdc":
            enrich_china_cdc_result(session, result, text)
        if not result.get("title") and not result.get("description") and not result.get("links"):
            snippet = clean_text(text[:400])
            result["snippet"] = snippet
        return result
    except requests.RequestException as exc:
        result["error"] = str(exc)
        return result


def fetch_data(source=None):
    session = build_session()
    if source:
        config = SOURCES[source]
        return {source: fetch_page(session, source, config)}
    return {name: fetch_page(session, name, config) for name, config in SOURCES.items()}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=sorted(SOURCES.keys()))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(json.dumps(fetch_data(source=args.source), ensure_ascii=False, indent=2))
