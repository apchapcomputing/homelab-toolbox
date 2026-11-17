#!/usr/bin/env python3
"""Print Wikipedia's Today's Featured Article (TFA).

Uses the Wikimedia REST "featured feed" endpoint. Standard library only.

Usage:
    wiki-article-of-the-day.py                 # today, English Wikipedia
    wiki-article-of-the-day.py --date 2026-01-15
    wiki-article-of-the-day.py --lang de       # only some wikis publish a TFA
    wiki-article-of-the-day.py --json          # raw TFA object for scripting
"""

import argparse
import datetime as dt
import json
import sys
import textwrap
import urllib.error
import urllib.request

API = "https://{lang}.wikipedia.org/api/rest_v1/feed/featured/{y}/{m:02d}/{d:02d}"
# Wikimedia asks automated clients to send a descriptive User-Agent.
USER_AGENT = "homelab-toolbox-wiki-aotd/1.0 (personal script)"


def fetch_tfa(date: dt.date, lang: str) -> dict:
    url = API.format(lang=lang, y=date.year, m=date.month, d=date.day)
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    tfa = data.get("tfa")
    if not tfa:
        raise LookupError(f"No featured article for {date} on {lang}.wikipedia.org")
    return tfa


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--date",
        type=dt.date.fromisoformat,
        default=None,
        help="YYYY-MM-DD (default: today in local time; see --utc)",
    )
    parser.add_argument(
        "--utc",
        action="store_true",
        help="use today's UTC date instead (matches Wikipedia's 00:00 UTC rollover)",
    )
    parser.add_argument("--lang", default="en", help="Wikipedia language code (default: en)")
    parser.add_argument("--json", action="store_true", help="print the raw TFA JSON")
    args = parser.parse_args()
    if args.date is None:
        args.date = (
            dt.datetime.now(dt.timezone.utc).date() if args.utc else dt.date.today()
        )

    try:
        tfa = fetch_tfa(args.date, args.lang)
    except urllib.error.HTTPError as e:
        print(f"error: HTTP {e.code} from Wikipedia API", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"error: could not reach Wikipedia: {e}", file=sys.stderr)
        return 1
    except LookupError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.json:
        json.dump(tfa, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return 0

    title = tfa.get("titles", {}).get("normalized") or tfa.get("title", "")
    url = tfa.get("content_urls", {}).get("desktop", {}).get("page", "")
    print(f"{title} ({args.date})")
    if tfa.get("description"):
        print(tfa["description"])
    print()
    print(textwrap.fill(tfa.get("extract", ""), width=80))
    print()
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
