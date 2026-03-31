#!/usr/bin/env python3
"""
compile_archive.py — Compiles a Twitter archive directory into a completely standalone single-file HTML viewer.
It embeds all standard external media references (images, videos) via Base64 into the JSON payload.

Usage:
    python compile_archive.py <path_to_archive_directory> [--out standalone.html]
"""

import sys
import json
import base64
import mimetypes
import argparse
import re
from pathlib import Path

def get_base64_data_uri(file_path: Path) -> str:
    if not file_path.exists():
        return ""
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        ext = file_path.suffix.lower()
        if ext in ('.mp4', '.m4v', '.webm'):
            mime_type = 'video/mp4'
        elif ext == '.gif':
            mime_type = 'image/gif'
        elif ext in ('.jpg', '.jpeg'):
            mime_type = 'image/jpeg'
        elif ext == '.png':
            mime_type = 'image/png'
        elif ext == '.webp':
            mime_type = 'image/webp'
        else:
            mime_type = 'application/octet-stream'

    with open(file_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode('utf-8')
    return f"data:{mime_type};base64,{b64}"

def main():
    parser = argparse.ArgumentParser(description="Compile a Twitter archive directory into a standalone single-file HTML.")
    parser.add_argument("archive_dir", help="Path to the scraped archive directory (e.g. twitter_archive/username)")
    parser.add_argument("--out", help="Output standalone HTML file path (default: standalone_archive.html in the same dir)")
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir).resolve()
    json_path = archive_dir / "archive.json"
    template_path = archive_dir / "viewer.html"

    if not json_path.exists():
        print(f"[!] {json_path} not found. Please provide a valid scrape directory.")
        sys.exit(1)
    if not template_path.exists():
        print(f"[!] {template_path} not found. Please provide a valid scrape directory.")
        sys.exit(1)

    out_path = Path(args.out).resolve() if args.out else archive_dir / "standalone_archive.html"

    print(f"[*] Loading data from {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        archive = json.load(f)

    print("[*] Encoding media to base64... (this might take a while for large videos)")

    # Encode avatar if it's local
    avatar = archive.get("profile", {}).get("avatar", "")
    if avatar and not avatar.startswith("http") and not avatar.startswith("data:"):
        full_avatar_path = archive_dir / avatar
        if full_avatar_path.exists():
            archive["profile"]["avatar"] = get_base64_data_uri(full_avatar_path)

    def process_tweet(t):
        if not t: return
        # Process media array
        if t.get("media"):
            for m in t["media"]:
                local_path = m.get("local")
                if local_path and not local_path.startswith("data:"):
                    full_media_path = archive_dir / local_path
                    if full_media_path.exists():
                        m["local"] = get_base64_data_uri(full_media_path)
        
        # Process avatar
        avatar = t.get("avatar")
        if avatar and not avatar.startswith("http") and not avatar.startswith("data:"):
            full_avatar_path = archive_dir / avatar
            if full_avatar_path.exists():
                t["avatar"] = get_base64_data_uri(full_avatar_path)

        # Recursively process linked tweets
        if t.get("parent_tweet"):
            process_tweet(t["parent_tweet"])
        if t.get("quoted_tweet"):
            process_tweet(t["quoted_tweet"])

    # Process all tweets in the archive
    for tweet in archive.get("tweets", []):
        process_tweet(tweet)

    print(f"[*] Reading template {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject the base64-enriched payload back into the HTML
    payload = json.dumps(archive, ensure_ascii=False)
    injection = f'<script>\nvar ARCHIVE_DATA = {payload};\n</script>\n</head>'

    # Attempt to replace the existing JSON payload block if present
    pattern = re.compile(r"<script>\s*var ARCHIVE_DATA = .*?;\s*</script>\s*</head>", re.DOTALL)
    if pattern.search(html):
        new_html = pattern.sub(injection, html, count=1)
    else:
        new_html = html.replace("</head>", injection, 1)

    print(f"[*] Saving standalone HTML to {out_path}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_html)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"[✓] Successfully wrote standalone archive ({size_mb:.1f} MB)")
    print(f"[✓] Open viewer: {out_path}")

if __name__ == "__main__":
    main()
