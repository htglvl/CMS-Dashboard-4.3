"""Return wiki content for a topic.

Usage:
    python tools/get_wiki.py --list
    python tools/get_wiki.py --topic risk
    python tools/get_wiki.py --search V2X
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = PROJECT_ROOT / "wiki"

TOPIC_MAP = {
    "home": "Home.md",
    "dashboard": "Dashboard-Guide.md",
    "risk": "Risk-Assessment.md",
    "spatial": "Spatial-Analysis.md",
    "api": "API-Reference.md",
    "cleaning": "Data-Cleaning.md",
}


def list_topics():
    topics = []
    for key, filename in sorted(TOPIC_MAP.items()):
        filepath = WIKI_DIR / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            description = ""
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("# ") and not stripped.startswith("## "):
                    description = stripped.lstrip("# ").strip()
                    break
            topics.append({"topic": key, "file": f"wiki/{filename}", "title": description})
        else:
            topics.append({"topic": key, "file": f"wiki/{filename}", "title": "(file not found)"})
    return topics


def get_topic_content(topic):
    topic_lower = topic.lower()
    if topic_lower not in TOPIC_MAP:
        return None, f"Unknown topic '{topic}'. Available: {', '.join(TOPIC_MAP.keys())}"
    filepath = WIKI_DIR / TOPIC_MAP[topic_lower]
    if not filepath.exists():
        return None, f"Wiki file not found: wiki/{TOPIC_MAP[topic_lower]}"
    return filepath.read_text(encoding="utf-8"), None


def search_wiki(keyword):
    results = []
    keyword_lower = keyword.lower()
    for topic_key, filename in TOPIC_MAP.items():
        filepath = WIKI_DIR / filename
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding="utf-8")
        matches = []
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if keyword_lower in line.lower():
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                matches.append({
                    "line_number": i + 1,
                    "matching_line": line.strip(),
                    "context": "\n".join(lines[start:end]),
                })
        if matches:
            results.append({"topic": topic_key, "file": f"wiki/{filename}",
                            "match_count": len(matches), "matches": matches[:5]})
    return results


def main():
    parser = argparse.ArgumentParser(description="Get wiki content.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--topic", type=str, help="Wiki topic to retrieve")
    group.add_argument("--search", type=str, help="Search keyword across wiki")
    group.add_argument("--list", action="store_true", help="List available topics")
    args = parser.parse_args()

    try:
        if args.list:
            output = {"topics": list_topics()}
        elif args.topic:
            content, error = get_topic_content(args.topic)
            if error:
                output = {"error": error}
            else:
                output = {"topic": args.topic.lower(), "content": content,
                          "file": f"wiki/{TOPIC_MAP[args.topic.lower()]}"}
        elif args.search:
            results = search_wiki(args.search)
            output = {"search_query": args.search, "total_files_matched": len(results), "results": results}

        print(json.dumps(output, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
