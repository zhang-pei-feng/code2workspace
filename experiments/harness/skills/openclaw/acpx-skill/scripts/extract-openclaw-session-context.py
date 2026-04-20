#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


def load_text() -> str:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        return Path(sys.argv[1]).read_text(encoding="utf-8")
    return sys.stdin.read()


def extract_value(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def extract_from_text(text: str) -> dict:
    return {
        "has_runtime_context": "OpenClaw runtime context (internal):" in text,
        "session_key": extract_value(r"^session_key:\s*(.+?)\s*$", text),
        "session_id": extract_value(r"^session_id:\s*(.+?)\s*$", text),
    }


def iter_embedded_texts(text: str):
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = obj.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                yield item["text"]


def main() -> int:
    text = load_text()
    result = extract_from_text(text)
    if result["session_key"] or result["session_id"]:
        print(json.dumps(result, ensure_ascii=False))
        return 0

    for embedded in iter_embedded_texts(text):
        candidate = extract_from_text(embedded)
        if candidate["session_key"] or candidate["session_id"]:
            print(json.dumps(candidate, ensure_ascii=False))
            return 0

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
