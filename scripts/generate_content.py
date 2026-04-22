#!/usr/bin/env python3
"""
CLI tool for generating marketing content with the StaffingAgent AI engine.

Usage:
    python scripts/generate_content.py --type linkedin --persona vp_ops --topic vms --count 5
    python scripts/generate_content.py --type email --persona cfo --sequence post_assessment
    python scripts/generate_content.py --type blog --persona vp_ops --topic middle_office
    python scripts/generate_content.py --type calendar --weeks 4
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def write_output(subdir: str, filename: str, content: str) -> Path:
    out_dir = OUTPUT_DIR / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def safe_print(text: str) -> None:
    """Print with fallback for Windows console encoding limitations."""
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def cmd_linkedin(args: argparse.Namespace) -> None:
    from src.marketing.content_engine import generate_linkedin_posts

    print(f"Generating {args.count} LinkedIn posts...")
    print(f"  Persona: {args.persona} | Topic: {args.topic}")
    print()

    content = generate_linkedin_posts(args.persona, args.topic, args.count)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{args.persona}_{args.topic}_{ts}.txt"
    path = write_output("linkedin", filename, content)

    safe_print(content)
    print(f"\nSaved to: {path}")


def cmd_email(args: argparse.Namespace) -> None:
    from src.marketing.content_engine import generate_email_sequence

    print(f"Generating email sequence: {args.sequence}")
    print(f"  Persona: {args.persona}")
    print()

    content = generate_email_sequence(args.persona, args.sequence)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{args.persona}_{args.sequence}_{ts}.txt"
    path = write_output("email", filename, content)

    safe_print(content)
    print(f"\nSaved to: {path}")


def cmd_blog(args: argparse.Namespace) -> None:
    from src.marketing.content_engine import generate_blog_outline

    print(f"Generating blog outline...")
    print(f"  Persona: {args.persona} | Topic: {args.topic}")
    print()

    keyword = args.keyword or ""
    content = generate_blog_outline(args.persona, args.topic, keyword=keyword)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{args.persona}_{args.topic}_{ts}.txt"
    path = write_output("blog", filename, content)

    safe_print(content)
    print(f"\nSaved to: {path}")


def cmd_calendar(args: argparse.Namespace) -> None:
    from src.marketing.calendar import (
        format_calendar_json,
        format_calendar_text,
        generate_calendar,
    )

    entries = generate_calendar(weeks=args.weeks, posts_per_week=args.posts_per_week)

    if args.format == "json":
        output = format_calendar_json(entries)
    else:
        output = format_calendar_text(entries)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "json" if args.format == "json" else "txt"
    filename = f"calendar_{args.weeks}wk_{ts}.{ext}"
    path = write_output(".", filename, output)

    print(output)
    print(f"\nSaved to: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="StaffingAgent.ai AI Content Generator",
    )
    sub = parser.add_subparsers(dest="type", required=True)

    # LinkedIn
    li = sub.add_parser("linkedin", help="Generate LinkedIn posts")
    li.add_argument("--persona", required=True, help="Persona key (vp_ops, cfo, cto)")
    li.add_argument("--topic", required=True, help="Topic key (vms, middle_office, etc.)")
    li.add_argument("--count", type=int, default=5, help="Number of posts (default: 5)")

    # Email
    em = sub.add_parser("email", help="Generate email sequence")
    em.add_argument("--persona", required=True, help="Persona key")
    em.add_argument(
        "--sequence", default="post_assessment",
        help="Sequence type (post_assessment, post_demo, cold_outbound)",
    )

    # Blog
    bl = sub.add_parser("blog", help="Generate blog outline")
    bl.add_argument("--persona", required=True, help="Persona key")
    bl.add_argument("--topic", required=True, help="Topic key")
    bl.add_argument("--keyword", default="", help="SEO target keyword (optional)")

    # Calendar
    cal = sub.add_parser("calendar", help="Generate content calendar")
    cal.add_argument("--weeks", type=int, default=4, help="Number of weeks (default: 4)")
    cal.add_argument("--posts-per-week", type=int, default=5, help="LinkedIn posts/week")
    cal.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args()

    handlers = {
        "linkedin": cmd_linkedin,
        "email": cmd_email,
        "blog": cmd_blog,
        "calendar": cmd_calendar,
    }

    handlers[args.type](args)


if __name__ == "__main__":
    main()
