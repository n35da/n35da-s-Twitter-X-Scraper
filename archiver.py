#!/usr/bin/env python3
"""
archiver.py — Twitter/X account archiver using gallery-dl.

CLI usage:
    python archiver.py <username> [options]

Options:
    --cookies <file>   Netscape cookies.txt for authenticated access
    --no-retweets      Skip retweets
    --no-replies       Skip the with_replies tab
    --no-quoted        Skip quoted tweets
    --no-videos        Skip video files
    --out <dir>        Output directory  (default: ./twitter_archive/<username>)
"""

import sys
import json
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Fix Unicode output on Windows (e.g. cp1252 can't encode ✓ or emoji)
if hasattr(sys.stdout, "reconfigure") and hasattr(sys.stdout, "buffer"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_OPTS = {
    "retweets": True,
    "replies":  True,
    "quoted":   True,
    "videos":   True,
}

# ── Dependency check ───────────────────────────────────────────────────────

def check_deps():
    """Verify gallery-dl is installed and reasonably up-to-date."""
    try:
        import gallery_dl
        ver = tuple(int(x) for x in gallery_dl.__version__.split(".")[:3])
        if ver < (1, 27, 0):
            print(f"[!] gallery-dl {gallery_dl.__version__} is outdated.")
            print("    Twitter/X scraping requires gallery-dl 1.27+.")
            print("    Run:  pip install -U gallery-dl")
            raise SystemExit(1)
    except ImportError:
        print("[!] gallery-dl is not installed.")
        print("    Run:  pip install gallery-dl")
        raise SystemExit(1)

# ── gallery-dl config ──────────────────────────────────────────────────────

def write_gdl_config(out_dir: Path, opts: dict) -> Path:
    """Write a gallery-dl JSON config for this run and return its path."""
    cfg = {
        "extractor": {
            "twitter": {
                "retweets":    opts.get("retweets", True),
                "videos":      opts.get("videos",   True),
                "quoted":      opts.get("quoted",   True),
                # NOTE: do NOT add a "replies" key here — newer gallery-dl
                # expects an object (not bool) and will warn/error.
                # Replies are handled by explicitly scraping the /with_replies URL.
                "text-tweets": True,  # include tweets with no media attached
            }
        },
        "output": {
            "progress": False,
            "log": {
                "level":  "warning",
                "format": "[gallery-dl] {levelname}: {message}",
            },
        },
    }
    path = out_dir / "gallery-dl-config.json"
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path

# ── gallery-dl runner ──────────────────────────────────────────────────────

def _run_gdl_url(cmd_base: list, url: str, label: str):
    """Run gallery-dl for one URL, streaming output line-by-line to stdout."""
    cmd = cmd_base + [url]
    print(f"\n[*] Scraping {label}")
    print(f"    {url}")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
    )
    for line in proc.stdout:
        print(line, end="", flush=True)
    proc.wait()
    if proc.returncode not in (0, 1):
        print(f"[!] gallery-dl exited with code {proc.returncode} for {label}")


def run_gallery_dl(username: str, out_dir: Path,
                   cookies_file: str = None, opts: dict = None):
    """
    Download tweets + media for *username* via gallery-dl.

    Two-pass strategy:
      Pass 1 — twitter.com/<username>              (tweets tab)
      Pass 2 — twitter.com/<username>/with_replies (replies tab, if enabled)

    Returns the media directory Path.
    """
    o = {**DEFAULT_OPTS, **(opts or {})}

    media_dir = out_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    cfg_path = write_gdl_config(out_dir, o)

    # When frozen by PyInstaller, sys.executable is the .exe — not Python.
    if getattr(sys, "frozen", False):
        python_exe = shutil.which("python") or shutil.which("python3") or "python"
    else:
        python_exe = sys.executable

    wrapper = (
        "import sys, json\n"
        "from pathlib import Path\n"
        "import gallery_dl, gallery_dl.config, gallery_dl.job\n"
        "_orig = gallery_dl.job.DownloadJob.handle_directory\n"
        "_out = Path(sys.argv.pop(1))\n"
        "def _serial(o):\n"
        "    if hasattr(o, 'isoformat'): return o.isoformat()\n"
        "    return str(o)\n"
        "def _new_handle(self, kwdict):\n"
        "    _orig(self, kwdict)\n"
        "    if kwdict and 'tweet_id' in kwdict:\n"
        "        try:\n"
        "            out = _out / f\"{kwdict['tweet_id']}.json\"\n"
        "            with open(out, 'w', encoding='utf-8') as f:\n"
        "                json.dump(dict(kwdict), f, default=_serial)\n"
        "        except Exception:\n"
        "            pass\n"
        "gallery_dl.job.DownloadJob.handle_directory = _new_handle\n"
        "sys.exit(gallery_dl.main())\n"
    )

    cmd_base = [
        python_exe, "-c", wrapper, str(media_dir),
        "--config",    str(cfg_path),
        "--directory", str(media_dir),
        "--filename",  "{tweet_id}_{num}.{extension}",
    ]

    if cookies_file:
        cmd_base += ["--cookies", cookies_file]
        print(f"[+] Using cookies: {cookies_file}")
    else:
        print("[!] No cookies — public tweets only (rate limits apply)")

    base_url = f"https://x.com/{username}"

    # Tweets pass — force a fresh check of every tweet
    _run_gdl_url(cmd_base + ["--no-skip"], base_url, f"@{username} (tweets)")

    # Replies pass — skip already-downloaded files to avoid rate-limiting
    if o["replies"]:
        _run_gdl_url(cmd_base, base_url + "/with_replies", f"@{username} (replies)")

    return media_dir

# ── Metadata collection ────────────────────────────────────────────────────

def _to_int(val, default=0):
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return default


def collect_metadata(media_dir: Path, username: str) -> list:
    """
    Read gallery-dl metadata JSON files from *media_dir* and return a list
    of tweet dicts sorted newest-first.

    The post-processor writes {tweet_id}.json for every tweet, including
    text-only tweets that produce no downloadable media.

    Two-pass approach:
      Pass 1 — collect raw JSON data keyed by tweet_id; associate media files
               by scanning non-JSON files with the {tweet_id}_{num}.{ext} pattern
      Pass 2 — build clean tweet records; link parent tweets via conversation_id
    """
    json_files = sorted(media_dir.glob("*.json"))
    if not json_files:
        return []

    print(f"[*] Found {len(json_files)} metadata files")

    # ── Build tweet_id → media files map ──────────────────────────────────
    # gallery-dl saves media as {tweet_id}_{num}.{extension}.
    # Scan every non-JSON file and key it by the tweet_id prefix so we can
    # attach the right files to each tweet record regardless of JSON format.
    media_by_tweet: dict[str, list] = {}
    for f in sorted(media_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() == ".json":
            continue
        parts = f.stem.split("_")
        if len(parts) >= 2 and parts[0].isdigit():
            media_by_tweet.setdefault(parts[0], []).append(f)

    # ── Pass 1 ────────────────────────────────────────────────────────────
    # The post-processor writes {tweet_id}.json for every tweet (including
    # text-only).  Old-style --write-metadata sidecars ({media}.json) are
    # also handled: tweet_id is read from the JSON data in both cases.
    raw: dict[str, dict] = {}

    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue

        tid = str(data.get("tweet_id") or data.get("id") or "").strip()
        # Fallback: if the file is named {tweet_id}.json the stem is the id
        if not tid and jf.stem.isdigit():
            tid = jf.stem
        if not tid:
            continue

        if tid not in raw:
            raw[tid] = {
                "data":  data,
                "files": media_by_tweet.get(tid, []),
            }

    print(f"[*] Found {len(raw)} tweet records in media folder")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _media_type(path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")
        if ext in ("mp4", "webm", "m4v"):
            return "video"
        if ext == "gif":
            return "gif"
        return "image"

    def build_media(files: list) -> list:
        items = []
        for path in sorted(files):
            items.append({
                "type":     _media_type(path),
                "local":    f"media/{path.name}",
                "original": "",
            })
        return items

    def build_parent(ref_id: str):
        if ref_id not in raw:
            return None
        p = raw[ref_id]["data"]
        pa = p.get("author") or {}
        pu = p.get("user")   or {}
        raw_date = p.get("date") or ""
        date_str = (str(raw_date).replace("T", " ").split("+")[0].split("Z")[0].strip()[:19])
        return {
            "id":       ref_id,
            "username": (pa.get("nick") or pu.get("nick") or ""),
            "handle":   (pa.get("name") or pu.get("name") or ""),
            "avatar":   (pa.get("profile_image") or pu.get("profile_image") or ""),
            "text":     (p.get("content") or p.get("text") or ""),
            "date":     date_str,
            "media":    build_media(raw[ref_id]["files"]),
        }

    # ── Pass 2 ────────────────────────────────────────────────────────────
    # gallery-dl populates author.nick for tweets that belong to *other*
    # users (context/thread tweets shown in a reply chain).  The target
    # user's own tweets typically have an empty author.nick.
    # With text-tweets:true, context tweets now get their own JSON files
    # and would otherwise flood the archive as standalone entries.
    # We keep them in `raw` (so build_parent can reference them) but exclude
    # them from the final tweet list.
    tweets = {}

    for tweet_id, rec in raw.items():
        data    = rec["data"]
        author  = data.get("author") or {}
        user    = data.get("user")   or {}

        is_retweet   = bool(data.get("retweet_id"))

        # Skip context tweets authored by someone other than the target user.
        # Check author handle ("name" in gallery-dl).
        # Retweets are exempt — their author handle is the original poster.
        author_handle = (author.get("name") or "").strip()
        if author_handle and author_handle.lower() != username.lower() and not is_retweet:
            continue
        conv_id      = str(data.get("conversation_id") or "").strip()
        reply_to_raw = data.get("reply_to") or []

        # Build reply_to_handles from the reply_to list
        reply_to_handles = []
        items = reply_to_raw if isinstance(reply_to_raw, list) else [reply_to_raw]
        for r in items:
            if isinstance(r, dict):
                h = (r.get("username") or r.get("nick") or r.get("name") or "").strip()
                if h:
                    reply_to_handles.append(h)
            elif isinstance(r, str) and r.strip():
                reply_to_handles.append(r.strip())

        is_reply = bool(reply_to_handles or (conv_id and conv_id != tweet_id))

        # Who retweeted (the user field on a retweet = person who RT'd)
        retweeted_by = ""
        if is_retweet:
            retweeted_by = (user.get("name") or author.get("name") or username)

        # Engagement counts — try several field-name conventions
        likes    = _to_int(data.get("favorite_count") or data.get("like_count")    or data.get("count_like")    or data.get("likes"))
        retweets = _to_int(data.get("retweet_count") or data.get("count_retweet") or data.get("retweets"))
        replies  = _to_int(data.get("reply_count")   or data.get("count_reply")   or data.get("replies"))
        views    = _to_int(data.get("view_count")    or data.get("count_view")    or data.get("views"))

        # Date — gallery-dl may give a datetime string or ISO format
        raw_date = data.get("date") or ""
        date_str = (str(raw_date)
                    .replace("T", " ")
                    .split("+")[0]
                    .split("Z")[0]
                    .strip()[:19])

        tweet = {
            "id":               tweet_id,
            # nick = @handle, name = display name
            "username":         (author.get("nick") or user.get("nick") or username),
            "handle":           (author.get("name") or user.get("name") or username),
            "avatar":           (author.get("profile_image") or user.get("profile_image") or ""),
            "text":             (data.get("content") or data.get("text") or ""),
            "date":             date_str,
            "likes":            likes,
            "retweets":         retweets,
            "replies":          replies,
            "views":            views,
            "is_reply":         is_reply,
            "reply_to_handles": reply_to_handles,
            "is_pinned":        bool(data.get("pinned_tweet")),
            "is_retweet":       is_retweet,
            "retweeted_by":     retweeted_by,
            "media":            build_media(rec["files"]),
            "parent_tweet":     None,
            "quoted_tweet":     None,
        }

        # Link to parent tweet via conversation_id
        if is_reply and conv_id and conv_id != tweet_id:
            tweet["parent_tweet"] = build_parent(conv_id)
            
        # Link to quoted tweet
        quote_id = str(data.get("quoted_status_id_str") or "")
        if quote_id == "0":
            quote_id = ""
            
        if not quote_id:
            for qid, qrec in raw.items():
                q_quote = str(qrec["data"].get("quote_id") or qrec["data"].get("quoted_by_id_str") or "")
                if q_quote and q_quote != "0" and q_quote == tweet_id:
                    quote_id = qid
                    break
        if quote_id and quote_id != tweet_id:
            tweet["quoted_tweet"] = build_parent(quote_id)

        tweets[tweet_id] = tweet

    sorted_tweets = sorted(tweets.values(), key=lambda t: t["date"], reverse=True)
    print(f"[+] Processed {len(sorted_tweets)} tweets")
    return sorted_tweets

# ── Archive saving ─────────────────────────────────────────────────────────

def save_archive(tweets: list, username: str, out_dir: Path):
    """
    Write archive.json and generate viewer.html with embedded data.
    Returns the path to viewer.html, or None if the template was missing.
    """
    # Use first tweet that belongs to the target user for profile info
    target = username.lower()
    profile_tweet = next(
        (t for t in tweets
         if t["username"].lower() == target or t["handle"].lower() == target),
        tweets[0] if tweets else {},
    )

    archive = {
        "profile": {
            "username": profile_tweet.get("username") or username,
            "handle":   profile_tweet.get("handle")   or username,
            "avatar":   profile_tweet.get("avatar")   or "",
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "tweet_count": len(tweets),
        },
        "tweets": tweets,
    }

    # Write archive.json
    json_path = out_dir / "archive.json"
    json_path.write_text(
        json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[+] Saved archive.json  ({len(tweets)} tweets)")

    # Locate viewer.html template
    script_dir = Path(getattr(sys, "_MEIPASS", "")) or Path(__file__).parent
    template_path = script_dir / "viewer.html"
    if not template_path.exists():
        template_path = Path(__file__).parent / "viewer.html"
    if not template_path.exists():
        print("[!] viewer.html template not found — skipping viewer generation")
        return None

    template = template_path.read_text(encoding="utf-8")

    # Inject data before </head>
    payload = json.dumps(archive, ensure_ascii=False)
    injection = f'<script>\nvar ARCHIVE_DATA = {payload};\n</script>\n</head>'
    html = template.replace("</head>", injection, 1)

    viewer_path = out_dir / "viewer.html"
    viewer_path.write_text(html, encoding="utf-8")
    print(f"[+] Saved viewer.html  → {viewer_path}")
    return viewer_path

# ── CLI entry point ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Archive a Twitter/X account's tweets and media."
    )
    parser.add_argument("username",        help="Twitter username (without @)")
    parser.add_argument("--cookies",       metavar="FILE",
                        help="Netscape cookies.txt for authenticated scraping")
    parser.add_argument("--no-retweets",   action="store_true", help="Skip retweets")
    parser.add_argument("--no-replies",    action="store_true", help="Skip the replies tab")
    parser.add_argument("--no-quoted",     action="store_true", help="Skip quoted tweets")
    parser.add_argument("--no-videos",     action="store_true", help="Skip video files")
    parser.add_argument("--out",           metavar="DIR",
                        help="Output directory (default: ./twitter_archive/<username>)")
    args = parser.parse_args()

    check_deps()

    username = args.username.lstrip("@")
    out_dir  = Path(args.out) if args.out else Path("twitter_archive") / username
    out_dir.mkdir(parents=True, exist_ok=True)

    opts = {
        "retweets": not args.no_retweets,
        "replies":  not args.no_replies,
        "quoted":   not args.no_quoted,
        "videos":   not args.no_videos,
    }

    print(f"[*] Archiving @{username}  →  {out_dir}")

    media_dir = run_gallery_dl(username, out_dir, cookies_file=args.cookies, opts=opts)

    print("\n[*] Collecting metadata from downloaded files...")
    tweets = collect_metadata(media_dir, username)

    if not tweets:
        print("[!] No tweet metadata found.")
        print("    The account may be private, rate-limited, or the handle is wrong.")
        return

    viewer_path = save_archive(tweets, username, out_dir)

    print(f"\n[✓] Done!  {len(tweets)} tweets archived → {out_dir}")
    if viewer_path:
        print(f"[✓] Open viewer: {viewer_path}")


if __name__ == "__main__":
    main()
