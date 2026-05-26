#!/usr/bin/env python3
import requests
import json
import argparse
import re
import sys
import os
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_MAX_RESULTS = 5
SESSIONS_INDEX = Path.home() / ".openclaw" / "agents" / "main" / "sessions" / "sessions.json"
SPRINGER_OA_KEY_ENV = "SPRINGER_OA_KEY"
PUBMED_API_KEY_ENV = "PUBMED_API_KEY"

QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "latest",
    "new",
    "not",
    "of",
    "on",
    "or",
    "paper",
    "papers",
    "preprint",
    "preprints",
    "research",
    "review",
    "study",
    "the",
    "to",
    "with",
    "title",
    "abstract",
    "journal",
    "mesh",
    "nature",
    "等",
    "论文",
    "文献",
    "最新",
    "研究",
}
TOPIC_REQUIREMENTS = [
    (
        {"sars-cov-2", "sars", "covid", "covid-19"},
        ("sars-cov-2", "sars cov 2", "covid-19", "covid 19", "covid"),
    ),
    ({"rsv"}, ("rsv", "respiratory syncytial")),
    ({"influenza", "flu"}, ("influenza", "flu")),
    ({"ebola"}, ("ebola",)),
    ({"mpox", "monkeypox"}, ("mpox", "monkeypox")),
]


def node_text(node):
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def parse_abstract(article):
    parts = []
    for abstract in article.findall(".//AbstractText"):
        text = node_text(abstract)
        if not text:
            continue
        label = abstract.attrib.get("Label")
        parts.append(f"{label}: {text}" if label else text)
    return "\n".join(parts)


def parse_pubmed_article(article):
    pmid = node_text(article.find(".//PMID"))
    journal = node_text(article.find(".//Journal/Title")) or node_text(article.find(".//ISOAbbreviation"))
    doi = ""
    for article_id in article.findall(".//ArticleId"):
        if article_id.attrib.get("IdType") == "doi":
            doi = node_text(article_id)
            break
    authors = []
    for author in article.findall(".//Author"):
        collective = node_text(author.find("CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        last = node_text(author.find("LastName"))
        fore = node_text(author.find("ForeName")) or node_text(author.find("Initials"))
        name = " ".join(part for part in [fore, last] if part)
        if name:
            authors.append(name)
    return {
        "pmid": pmid,
        "title": node_text(article.find(".//ArticleTitle")),
        "journal": journal,
        "pubdate": parse_pubmed_pubdate(article),
        "doi": doi,
        "authors": authors,
        "abstract": parse_abstract(article),
        "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    }


def parse_pubmed_pubdate(article):
    pub_date = article.find(".//JournalIssue/PubDate")
    if pub_date is None:
        return ""
    medline = node_text(pub_date.find("MedlineDate"))
    if medline:
        return medline
    parts = [node_text(pub_date.find(tag)) for tag in ("Year", "Month", "Day")]
    return " ".join(part for part in parts if part)


def api_key_params(env_name, param_name="api_key"):
    api_key = os.environ.get(env_name, "").strip()
    return {param_name: api_key} if api_key else {}


def relevance_terms(query):
    query = re.sub(r"\[[^\]]+\]", " ", query or "")
    raw_terms = re.findall(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*|[\u4e00-\u9fff]{2,}", query.lower())
    terms = []
    for term in raw_terms:
        term = term.strip(".-")
        if len(term) < 2 or term in QUERY_STOPWORDS:
            continue
        terms.append(term)
        for part in re.split(r"[-.]", term):
            if len(part) >= 3 and part not in QUERY_STOPWORDS:
                terms.append(part)
    seen = set()
    unique = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return unique


def record_relevance_score(record, terms, *, fields):
    title = str(record.get("title", "")).lower()
    weighted_fields = [(title, 4)]
    for field in fields:
        if field == "title":
            continue
        value = record.get(field, "")
        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        weighted_fields.append((str(value).lower(), 1 if field in {"journal", "publicationName"} else 2))

    score = 0
    for term in terms:
        for text, weight in weighted_fields:
            if term in text:
                score += weight
                break
    return score


def searchable_record_text(record, fields):
    values = []
    for field in ("title", *fields):
        value = record.get(field, "")
        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        values.append(str(value))
    return " ".join(values).lower().replace("-", " ")


def required_topic_needles(terms):
    term_set = set(terms)
    for triggers, needles in TOPIC_REQUIREMENTS:
        if term_set & triggers:
            return needles
    return ()


def rank_records(records, query, *, fields, limit=None, min_score=1):
    terms = relevance_terms(query)
    if not terms:
        return list(records[:limit] if limit is not None else records)

    topic_needles = required_topic_needles(terms)
    scored = []
    for index, record in enumerate(records):
        if topic_needles:
            haystack = searchable_record_text(record, fields)
            if not any(needle in haystack for needle in topic_needles):
                continue
        score = record_relevance_score(record, terms, fields=fields)
        if score >= min_score:
            item = dict(record)
            item["_relevance_score"] = score
            scored.append((score, index, item))
    scored.sort(key=lambda item: (-item[0], item[1]))
    ranked = [item for _, _, item in scored]
    return ranked[:limit] if limit is not None else ranked


def fetch_pubmed_details(pmids):
    if not pmids:
        return []
    sum_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    params.update(api_key_params(PUBMED_API_KEY_ENV))
    resp = get_with_session_fallback(sum_url, params=params, timeout=15, prefer_direct=True)
    root = ET.fromstring(resp.text)
    parsed = [parse_pubmed_article(article) for article in root.findall(".//PubmedArticle")]
    by_pmid = {item.get("pmid"): item for item in parsed}
    return [by_pmid[pmid] for pmid in pmids if pmid in by_pmid]


def springer_abstract(record):
    abstract = record.get("abstract", "")
    if isinstance(abstract, dict):
        texts = []
        for value in abstract.values():
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, list):
                texts.extend(str(item) for item in value)
        return "\n".join(texts)
    return str(abstract) if abstract else ""


def springer_url(record):
    urls = record.get("url") or []
    if isinstance(urls, list):
        for item in urls:
            if isinstance(item, dict) and item.get("value"):
                return item["value"]
            if isinstance(item, str):
                return item
    return ""


def build_session():
    session = requests.Session()
    session.trust_env = False

    proxies = {}
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    if proxies:
        session.proxies.update(proxies)
    return session


def build_direct_session():
    session = requests.Session()
    session.trust_env = False
    return session


def get_with_session_fallback(url, *, params=None, timeout=10, prefer_direct=False):
    sessions = [build_direct_session(), build_session()] if prefer_direct else [build_session(), build_direct_session()]
    last_error = None
    for session in sessions:
        try:
            resp = session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_error = exc
    raise last_error


def infer_max_results_from_recent_request():
    try:
        with SESSIONS_INDEX.open("r", encoding="utf-8") as handle:
            sessions = json.load(handle)
        session_file = sessions.get("agent:main:main", {}).get("sessionFile")
        candidates = []
        if session_file:
            candidates.append(Path(session_file))
        sessions_dir = SESSIONS_INDEX.parent
        if sessions_dir.exists():
            candidates.extend(sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True))
        seen = set()
        patterns = [
            r"只返回\s*(\d+)",
            r"返回\s*(\d+)\s*篇",
            r"(\d+)\s*篇论文",
            r"top\s*(\d+)",
            r"(\d+)\s*(?:papers|results)",
        ]
        for candidate in candidates:
            if candidate in seen or not candidate.exists():
                continue
            seen.add(candidate)
            with candidate.open("r", encoding="utf-8") as handle:
                for raw_line in reversed(handle.readlines()[-40:]):
                    try:
                        payload = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    message = payload.get("message", {})
                    if payload.get("type") != "message" or message.get("role") != "user":
                        continue
                    parts = message.get("content", [])
                    text = "\n".join(part.get("text", "") for part in parts if part.get("type") == "text")
                    for pattern in patterns:
                        match = re.search(pattern, text, flags=re.IGNORECASE)
                        if match:
                            value = int(match.group(1))
                            if value > 0:
                                return value
    except Exception:
        return None
    return None


def resolve_max_results(value):
    if value is not None:
        return value
    inferred = infer_max_results_from_recent_request()
    if inferred is not None:
        return inferred
    return DEFAULT_MAX_RESULTS

def search_pubmed(query, max_results=5, details=False):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    pool_size = min(max(max_results * 3, max_results), 50)
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": pool_size}
    params.update(api_key_params(PUBMED_API_KEY_ENV))
    try:
        resp = get_with_session_fallback(url, params=params, timeout=10, prefer_direct=True)
        id_list = resp.json().get("esearchresult", {}).get("idlist", [])
        if not id_list: return json.dumps({"error": "No papers found in PubMed."})
        if details:
            records = fetch_pubmed_details(id_list)
            results = rank_records(
                records,
                query,
                fields=("title", "abstract", "journal"),
                limit=max_results,
                min_score=1,
            )
            if not results:
                return json.dumps({"error": "No PubMed papers passed the relevance filter.", "query": query})
            return json.dumps(results, ensure_ascii=False, indent=2)
            
        sum_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        sum_params = {"db": "pubmed", "id": ",".join(id_list), "retmode": "json"}
        sum_params.update(api_key_params(PUBMED_API_KEY_ENV))
        sum_resp = get_with_session_fallback(sum_url, params=sum_params, timeout=10, prefer_direct=True)
        summary_data = sum_resp.json().get("result", {})
        
        results = []
        for uid in id_list:
            if uid in summary_data:
                paper = summary_data[uid]
                results.append({
                    "pmid": uid,
                    "title": paper.get("title", ""),
                    "pubdate": paper.get("pubdate", ""),
                    "link": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
                })
        results = rank_records(results, query, fields=("title", "journal"), limit=max_results, min_score=1)
        if not results:
            return json.dumps({"error": "No PubMed papers passed the relevance filter.", "query": query})
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e: return json.dumps({"error": str(e)})

def search_springer(query, max_results=5, details=False):
    if not os.environ.get(SPRINGER_OA_KEY_ENV, "").strip():
        return json.dumps({"error": f"Missing Springer Nature API key. Set {SPRINGER_OA_KEY_ENV} in the environment."})

    url = "https://api.springernature.com/openaccess/json"
    pool_size = min(max(max_results * 4, max_results), 50)
    params = {"q": query, "p": pool_size}
    params.update(api_key_params(SPRINGER_OA_KEY_ENV))
    try:
        resp = get_with_session_fallback(url, params=params, timeout=10)
        records = resp.json().get("records", [])
        if not records: return json.dumps({"error": "No papers found in Springer."})

        results = [
            {
                "title": r.get("title", ""),
                "date": r.get("publicationDate", ""),
                "journal": r.get("publicationName", ""),
                "doi": r.get("doi", ""),
                "authors": [
                    creator.get("creator", "")
                    for creator in r.get("creators", [])
                    if isinstance(creator, dict) and creator.get("creator")
                ],
                "abstract": springer_abstract(r),
                "link": springer_url(r),
            }
            for r in records
        ]
        results = rank_records(results, query, fields=("title", "abstract", "journal"), limit=max_results, min_score=2)
        if not results:
            return json.dumps({"error": "No Springer papers passed the relevance filter.", "query": query})
        if not details:
            results = [{"title": r.get("title", ""), "date": r.get("date", ""), "doi": r.get("doi", ""), "_relevance_score": r.get("_relevance_score")} for r in results]
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e: return json.dumps({"error": str(e)})

def search_biorxiv(start_date, end_date, max_results=5, details=False, query=None):
    url = f"https://api.biorxiv.org/details/biorxiv/{start_date}/{end_date}"
    try:
        resp = get_with_session_fallback(url, timeout=15)
        collection = resp.json().get("collection", [])
        if not collection: return json.dumps({"error": "No preprints found."})

        results = [
            {
                "title": p.get("title", ""),
                "date": p.get("date", ""),
                "doi": p.get("doi", ""),
                "authors": p.get("authors", ""),
                "category": p.get("category", ""),
                "abstract": p.get("abstract", ""),
                "jatsxml": p.get("jatsxml", ""),
                "link": f"https://www.biorxiv.org/content/{p.get('doi', '')}v{p.get('version', '')}" if p.get("doi") else "",
            }
            for p in collection
        ]
        if query:
            results = rank_records(results, query, fields=("title", "abstract", "category"), limit=max_results, min_score=1)
            if not results:
                return json.dumps({"error": "No bioRxiv preprints passed the relevance filter.", "query": query})
        else:
            results = results[:max_results]
        if not details:
            results = [{"title": p.get("title", ""), "date": p.get("date", ""), "doi": p.get("doi", ""), "_relevance_score": p.get("_relevance_score")} for p in results]
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e: return json.dumps({"error": str(e)})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Academic Search CLI for OpenClaw")
    parser.add_argument("--source", choices=["pubmed", "springer", "biorxiv"], required=True, help="The database to search")
    parser.add_argument("--query", type=str, help="Search keywords; required for pubmed/springer and optional relevance filter for biorxiv")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD (required for biorxiv)")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD (required for biorxiv)")
    parser.add_argument("--max-results", type=int, default=None, help="Maximum number of results to return")
    parser.add_argument("--details", action="store_true", help="Return richer details such as abstracts, authors, journal/category, DOI, and links when available")
    parser.add_argument("--include-abstracts", action="store_true", help="Alias for --details")
    
    args = parser.parse_args()
    
    max_results = resolve_max_results(args.max_results)
    details = args.details or args.include_abstracts

    if args.source == "pubmed":
        if not args.query: print(json.dumps({"error": "Missing --query"})); sys.exit(1)
        print(search_pubmed(args.query, max_results=max_results, details=details))
    elif args.source == "springer":
        if not args.query: print(json.dumps({"error": "Missing --query"})); sys.exit(1)
        print(search_springer(args.query, max_results=max_results, details=details))
    elif args.source == "biorxiv":
        if not args.start or not args.end: print(json.dumps({"error": "Missing --start or --end"})); sys.exit(1)
        print(search_biorxiv(args.start, args.end, max_results=max_results, details=details, query=args.query))
