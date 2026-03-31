#!/usr/bin/env python3
"""
gui.py — Tkinter GUI for the Twitter Archiver.
Run directly:  python gui.py
Or build exe:  python -m PyInstaller --onefile --windowed --name TwitterArchiver gui.py
"""

import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

import archiver as _archiver

# ── Theme constants ────────────────────────────────────────────────────────
BG   = "#000000"
CARD = "#16181c"
FG   = "#e7e9ea"
SUB  = "#71767b"
ACC  = "#1d9bf0"
PAD  = 16

FONT      = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")

# Output lives next to the script (or exe) so paths are always absolute
if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).resolve().parent

DEFAULT_OUT = _BASE / "twitter_archive"


# ── Stdout redirect ────────────────────────────────────────────────────────

class _StdoutRedirect:
    """Forwards sys.stdout.write() calls into the GUI log callback."""

    def __init__(self, callback):
        self._cb = callback
        self.encoding = "utf-8"
        self.errors   = "replace"

    def write(self, text):
        if text:
            self._cb(text)

    def flush(self):
        pass


# ── Main application ───────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Twitter Archiver")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(540, 580)

        self._stop_event  = threading.Event()
        self._viewer_path = None

        # Option BooleanVars — initialised here so they always exist
        self._opt_retweets = tk.BooleanVar(value=True)
        self._opt_replies  = tk.BooleanVar(value=True)
        self._opt_quoted   = tk.BooleanVar(value=True)
        self._opt_videos   = tk.BooleanVar(value=True)

        self._opts_visible = False
        self._opts_frame   = None

        self._build_ui()
        self.after(100, lambda: self.geometry("560x660"))

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        # Title
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=PAD, pady=(PAD, 4))
        tk.Label(hdr, text="Twitter Archiver",
                 font=("Segoe UI", 18, "bold"), bg=BG, fg=FG).pack(side="left")

        # ── Input card ────────────────────────────────────────────────────
        card = tk.Frame(self, bg=CARD, bd=0, relief="flat")
        card.pack(fill="x", padx=PAD, pady=(4, 0))
        card.columnconfigure(0, weight=1)

        # Username row
        tk.Label(card, text="Target username", font=FONT_BOLD,
                 bg=CARD, fg=SUB).grid(row=0, column=0, sticky="w",
                                       padx=PAD, pady=(12, 2))
        self._username_var = tk.StringVar()
        urow = tk.Frame(card, bg=CARD)
        urow.grid(row=1, column=0, sticky="ew", padx=PAD, pady=(0, 4))
        tk.Label(urow, text="@", font=("Segoe UI", 12),
                 bg=CARD, fg=SUB).pack(side="left")
        tk.Entry(urow, textvariable=self._username_var,
                 font=FONT, bg="#16181c", fg=FG, insertbackground=FG,
                 relief="flat", bd=4, width=28).pack(side="left", fill="x", expand=True)

        # Cookies row
        tk.Label(card, text="File path to cookies.txt",
                 font=FONT_BOLD, bg=CARD, fg=SUB).grid(
            row=2, column=0, sticky="w", padx=PAD, pady=(12, 2))

        cookie_row = tk.Frame(card, bg=CARD)
        cookie_row.grid(row=3, column=0, sticky="ew", padx=PAD, pady=(0, PAD))

        self._cookies_var = tk.StringVar()
        tk.Entry(cookie_row, textvariable=self._cookies_var,
                 font=FONT, bg="#16181c", fg=FG, insertbackground=FG,
                 relief="flat", bd=4, width=30).pack(side="left", fill="x", expand=True)
        tk.Button(cookie_row, text="Browse cookies.txt…",
                  command=self._browse_cookies,
                  font=FONT, bg="#2f3336", fg=FG,
                  activebackground="#3a3d42", activeforeground=FG,
                  relief="flat", cursor="hand2", padx=8).pack(side="left", padx=(6, 0))

        # ── Options toggle ─────────────────────────────────────────────────
        opts_hdr = tk.Frame(self, bg=BG)
        opts_hdr.pack(fill="x", padx=PAD, pady=(6, 0))
        self._opts_btn = tk.Button(
            opts_hdr, text="Options ▸", command=self._toggle_opts,
            font=FONT, bg=BG, fg=SUB, activebackground=BG, activeforeground=FG,
            relief="flat", cursor="hand2", bd=0)
        self._opts_btn.pack(side="left")

        # ── Action buttons ─────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=PAD, pady=(10, 0))

        self._start_btn = tk.Button(
            btn_row, text="Start Scraping", command=self._start_scraping,
            font=("Segoe UI", 11, "bold"), bg=ACC, fg="#ffffff",
            activebackground="#1a8cd8", activeforeground="#ffffff",
            relief="flat", cursor="hand2", padx=16, pady=8)
        self._start_btn.pack(side="left")

        self._stop_btn = tk.Button(
            btn_row, text="◼  Stop", command=self._stop_scraping,
            font=("Segoe UI", 11), bg="#2f3336", fg=FG,
            activebackground="#3a3d42", activeforeground=FG,
            relief="flat", cursor="hand2", padx=16, pady=8, state="disabled")
        self._stop_btn.pack(side="left", padx=(8, 0))

        self._open_btn = tk.Button(
            btn_row, text="Open Viewer", command=self._open_viewer,
            font=("Segoe UI", 11), bg="#2f3336", fg="#71767b",
            activebackground="#3a3d42", activeforeground=FG,
            relief="flat", cursor="hand2", padx=16, pady=8, state="disabled")
        self._open_btn.pack(side="right")

        # Status bar
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._status_var,
                 font=("Segoe UI", 9), bg=BG, fg=SUB,
                 anchor="w").pack(fill="x", padx=PAD, pady=(6, 0))

        # ── Log ────────────────────────────────────────────────────────────
        log_frame = tk.Frame(self, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))

        self._log = tk.Text(
            log_frame, font=("Consolas", 9), bg="#0d1117", fg="#c9d1d9",
            insertbackground=FG, relief="flat", bd=0,
            wrap="word", state="disabled")
        sb = tk.Scrollbar(log_frame, command=self._log.yview, bg="#2f3336")
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(side="left", fill="both", expand=True)

    # ── Options panel ──────────────────────────────────────────────────────

    def _toggle_opts(self):
        self._opts_visible = not self._opts_visible
        if self._opts_visible:
            self._opts_btn.configure(text="⚙  Options ▾")
            self._opts_frame = tk.Frame(self, bg=CARD)
            self._opts_frame.pack(fill="x", padx=PAD, pady=(4, 0))
            for i, (var, label) in enumerate([
                (self._opt_retweets, "Include retweets"),
                (self._opt_replies,  "Include replies"),
                (self._opt_quoted,   "Include quoted tweets"),
                (self._opt_videos,   "Include videos"),
            ]):
                tk.Checkbutton(
                    self._opts_frame, text=label, variable=var,
                    font=FONT, bg=CARD, fg=FG, selectcolor="#16181c",
                    activebackground=CARD, activeforeground=FG,
                    relief="flat",
                ).grid(row=i // 2, column=i % 2, sticky="w", padx=PAD, pady=4)
        else:
            self._opts_btn.configure(text="⚙  Options ▸")
            if self._opts_frame:
                self._opts_frame.destroy()
                self._opts_frame = None

    # ── File browser ───────────────────────────────────────────────────────

    def _browse_cookies(self):
        path = filedialog.askopenfilename(
            title="Select cookies.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._cookies_var.set(path)

    # ── Scraping control ───────────────────────────────────────────────────

    def _set_running(self, running: bool):
        if running:
            self._start_btn.configure(state="disabled")
            self._stop_btn.configure(state="normal")
        else:
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")

    def _log_write(self, text: str):
        """Thread-safe log append."""
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", text if text.endswith("\n") else text + "\n")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _start_scraping(self):
        username = self._username_var.get().strip().lstrip("@")
        if not username:
            messagebox.showwarning("Missing input", "Please enter a target username.")
            return

        cookies = self._cookies_var.get().strip() or None
        opts = {
            "retweets": self._opt_retweets.get(),
            "replies":  self._opt_replies.get(),
            "quoted":   self._opt_quoted.get(),
            "videos":   self._opt_videos.get(),
        }

        # Clear log
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

        self._open_btn.configure(state="disabled", fg="#71767b")
        self._viewer_path = None
        self._stop_event.clear()
        self._set_running(True)
        self._status_var.set(f"Scraping @{username} …")

        threading.Thread(
            target=self._scrape_thread,
            args=(username, cookies, opts),
            daemon=True,
        ).start()

    def _stop_scraping(self):
        self._stop_event.set()
        self._status_var.set("Stopping…")

    def _scrape_thread(self, username: str, cookies, opts: dict):
        self._log_write(f"[*] Running archiver for @{username}")
        self._log_write(f"[+] Cookies: {cookies}" if cookies
                        else "[!] No cookies — public tweets only")
        self._log_write("")

        out_dir = DEFAULT_OUT / username
        out_dir.mkdir(parents=True, exist_ok=True)

        old_stdout = sys.stdout
        sys.stdout = _StdoutRedirect(self._log_write)
        try:
            try:
                _archiver.check_deps()
            except SystemExit:
                self._log_write("[!] gallery-dl missing or outdated.")
                self._log_write("    Run:  pip install -U gallery-dl")
                return

            media_dir = _archiver.run_gallery_dl(
                username, out_dir, cookies_file=cookies, opts=opts
            )

            self._log_write("\n[*] Collecting metadata from downloaded files...")
            tweets = _archiver.collect_metadata(media_dir, username)

            if not tweets:
                self._log_write("[!] No tweet metadata found.")
                self._log_write(
                    "    Account may be private, rate-limited, or the handle doesn't exist."
                )
            else:
                _archiver.save_archive(tweets, username, out_dir)
                self._viewer_path = str(out_dir / "viewer.html")
                self.after(0, lambda: self._open_btn.configure(state="normal", fg=FG))
                self._log_write(f"\n[✓] Done!  {len(tweets)} tweets archived.")
                self._log_write(f"[✓] Viewer: {self._viewer_path}")

        except Exception as exc:
            self._log_write(f"[!] Unexpected error: {exc}")
        finally:
            sys.stdout = old_stdout
            self.after(0, lambda: self._set_running(False))
            self.after(0, lambda: self._status_var.set("Ready"))

    # ── Open viewer ────────────────────────────────────────────────────────

    def _open_viewer(self):
        if self._viewer_path:
            # as_uri() produces a correct absolute file:// URL on all platforms
            webbrowser.open(Path(self._viewer_path).resolve().as_uri())


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
