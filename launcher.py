#!/usr/bin/env python3
"""
TRUTHFORGE AI — Desktop Launcher
Starts and stops the Streamlit server from a GUI window.
No terminal required.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import webbrowser
import os
import sys
import time
import signal
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.resolve()
APP_URL      = "http://localhost:8501"
PYTHON       = sys.executable          # same Python that's running this script

# ── Colour palette ────────────────────────────────────────────────────────────
BG           = "#0d1117"
BG_PANEL     = "#161b22"
BG_CARD      = "#21262d"
ACCENT       = "#c9a84c"   # gold
ACCENT_BLUE  = "#58a6ff"
TEXT         = "#e6edf3"
TEXT_DIM     = "#8b949e"
GREEN        = "#3fb950"
RED          = "#f85149"
YELLOW       = "#d29922"
BORDER       = "#30363d"


class TruthforgeLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._ready = False

        self._build_window()
        self._build_ui()
        self._check_env_on_start()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Window ────────────────────────────────────────────────────────────────
    def _build_window(self):
        self.title("TRUTHFORGE AI")
        self.geometry("640x540")
        self.minsize(560, 460)
        self.configure(bg=BG)
        try:                                   # macOS icon via iconphoto
            icon = tk.PhotoImage(data=_ICON_B64)
            self.iconphoto(True, icon)
        except Exception:
            pass

    # ── UI layout ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ─ Title bar area ─────────────────────────────────────────────────────
        header = tk.Frame(self, bg=BG, pady=20)
        header.pack(fill="x")

        tk.Label(
            header, text="⚖", font=("Helvetica", 32), bg=BG, fg=ACCENT
        ).pack()
        tk.Label(
            header, text="TRUTHFORGE AI",
            font=("Helvetica", 20, "bold"), bg=BG, fg=TEXT
        ).pack()
        tk.Label(
            header, text="Forging Truth from Legal Testimony",
            font=("Helvetica", 10), bg=BG, fg=TEXT_DIM
        ).pack(pady=(2, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=24, pady=8)

        # ─ Status card ────────────────────────────────────────────────────────
        status_frame = tk.Frame(self, bg=BG_CARD, bd=0, relief="flat")
        status_frame.pack(fill="x", padx=24, pady=(0, 12))
        _rounded_border(status_frame)

        inner = tk.Frame(status_frame, bg=BG_CARD, padx=18, pady=14)
        inner.pack(fill="x")

        # Status LED + label
        led_row = tk.Frame(inner, bg=BG_CARD)
        led_row.pack(anchor="w")

        self._led = tk.Canvas(
            led_row, width=12, height=12, bg=BG_CARD, highlightthickness=0
        )
        self._led.pack(side="left", padx=(0, 8))
        self._led_oval = self._led.create_oval(2, 2, 10, 10, fill=RED, outline="")

        self._status_var = tk.StringVar(value="Server not running")
        tk.Label(
            led_row, textvariable=self._status_var,
            font=("Helvetica", 12, "bold"), bg=BG_CARD, fg=TEXT
        ).pack(side="left")

        # URL
        url_row = tk.Frame(inner, bg=BG_CARD)
        url_row.pack(anchor="w", pady=(6, 0))
        tk.Label(
            url_row, text="URL:", font=("Helvetica", 10),
            bg=BG_CARD, fg=TEXT_DIM
        ).pack(side="left")
        self._url_lbl = tk.Label(
            url_row, text=APP_URL, font=("Helvetica", 10),
            bg=BG_CARD, fg=TEXT_DIM, cursor="hand2"
        )
        self._url_lbl.pack(side="left", padx=(6, 0))
        self._url_lbl.bind("<Button-1>", lambda _: self._open_browser())

        # ─ Buttons ────────────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=24, pady=(0, 12))

        self._start_btn = _make_btn(
            btn_frame, "▶  Start Server", ACCENT, "#1a1000",
            command=self._start_server
        )
        self._start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self._stop_btn = _make_btn(
            btn_frame, "■  Stop Server", BG_CARD, TEXT,
            command=self._stop_server, state="disabled"
        )
        self._stop_btn.pack(side="left", expand=True, fill="x", padx=(6, 6))

        self._browser_btn = _make_btn(
            btn_frame, "↗  Open Browser", ACCENT_BLUE, "#001020",
            command=self._open_browser, state="disabled"
        )
        self._browser_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        # ─ Log ────────────────────────────────────────────────────────────────
        log_header = tk.Frame(self, bg=BG)
        log_header.pack(fill="x", padx=24)
        tk.Label(
            log_header, text="SERVER LOG",
            font=("Helvetica", 9, "bold"), bg=BG, fg=TEXT_DIM
        ).pack(side="left")
        self._clear_btn = tk.Label(
            log_header, text="Clear", font=("Helvetica", 9),
            bg=BG, fg=ACCENT_BLUE, cursor="hand2"
        )
        self._clear_btn.pack(side="right")
        self._clear_btn.bind("<Button-1>", lambda _: self._clear_log())

        log_outer = tk.Frame(self, bg=BORDER, bd=1)
        log_outer.pack(fill="both", expand=True, padx=24, pady=(4, 16))

        self._log = scrolledtext.ScrolledText(
            log_outer,
            wrap="word",
            bg=BG_PANEL,
            fg=TEXT_DIM,
            font=("Menlo", 9) if sys.platform == "darwin" else ("Consolas", 9),
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            state="disabled",
        )
        self._log.pack(fill="both", expand=True)

        # colour tags for log lines
        self._log.tag_configure("info",  foreground=TEXT_DIM)
        self._log.tag_configure("ok",    foreground=GREEN)
        self._log.tag_configure("warn",  foreground=YELLOW)
        self._log.tag_configure("error", foreground=RED)
        self._log.tag_configure("head",  foreground=ACCENT)

    # ── Env check ─────────────────────────────────────────────────────────────
    def _check_env_on_start(self):
        missing = []
        try:
            import streamlit  # noqa: F401
        except ImportError:
            missing.append("streamlit")

        env_file = PROJECT_ROOT / ".env"
        if not env_file.exists():
            example = PROJECT_ROOT / ".env.example"
            if example.exists():
                import shutil
                shutil.copy(example, env_file)
                self._log_line(
                    "ℹ  Created .env from .env.example — add your API key(s) inside.",
                    "warn"
                )
            else:
                self._log_line("⚠  No .env file found.", "warn")

        if missing:
            self._log_line(
                f"⚠  Missing packages: {', '.join(missing)}.\n"
                "   Run:  pip install -r requirements.txt",
                "warn"
            )
            self._start_btn.configure(state="disabled")
        else:
            self._log_line("✓  Environment ready. Click Start Server to begin.", "ok")

    # ── Server start / stop ───────────────────────────────────────────────────
    def _start_server(self):
        if self._proc and self._proc.poll() is None:
            return  # already running

        self._ready = False
        self._set_status("Starting…", YELLOW)
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._log_line("\n─── Starting TRUTHFORGE AI ───", "head")

        try:
            self._proc = subprocess.Popen(
                [PYTHON, "-m", "streamlit", "run", "main.py",
                 "--server.headless", "true",
                 "--server.port", "8501"],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self._log_line(f"✗  Failed to start: {exc}", "error")
            self._set_status("Start failed", RED)
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            return

        self._reader_thread = threading.Thread(
            target=self._read_output, daemon=True
        )
        self._reader_thread.start()

        # Poll until ready (timeout 60 s)
        threading.Thread(target=self._wait_for_ready, daemon=True).start()

    def _stop_server(self):
        if self._proc and self._proc.poll() is None:
            self._log_line("\n─── Stopping server ───", "head")
            try:
                # Graceful → forceful
                os.kill(self._proc.pid, signal.SIGTERM)
                for _ in range(30):
                    if self._proc.poll() is not None:
                        break
                    time.sleep(0.1)
                if self._proc.poll() is None:
                    self._proc.kill()
            except Exception:
                pass

        self._proc = None
        self._ready = False
        self._set_status("Server not running", RED)
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._browser_btn.configure(state="disabled")
        self._url_lbl.configure(fg=TEXT_DIM)
        self._log_line("✓  Server stopped.", "ok")

    def _read_output(self):
        """Read subprocess stdout and write to log widget."""
        if not self._proc:
            return
        try:
            for line in self._proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                tag = "info"
                if any(k in line for k in ("Error", "ERROR", "Exception")):
                    tag = "error"
                elif any(k in line for k in ("Warning", "WARNING")):
                    tag = "warn"
                elif any(k in line for k in ("You can now view", "Network URL", "Local URL")):
                    tag = "ok"
                self._log_line(line, tag)
        except Exception:
            pass

    def _wait_for_ready(self):
        """Poll until Streamlit is listening, then update UI."""
        import urllib.request, urllib.error
        deadline = time.time() + 60
        while time.time() < deadline:
            if self._proc and self._proc.poll() is not None:
                self.after(0, lambda: self._set_status("Crashed", RED))
                return
            try:
                urllib.request.urlopen(APP_URL, timeout=2)
                self._ready = True
                self.after(0, self._on_server_ready)
                return
            except Exception:
                time.sleep(0.5)
        # Timeout
        self.after(0, lambda: self._set_status("Timeout — check log", YELLOW))

    def _on_server_ready(self):
        self._set_status("Running  •  http://localhost:8501", GREEN)
        self._browser_btn.configure(state="normal")
        self._url_lbl.configure(fg=ACCENT_BLUE)
        self._log_line(f"✓  TRUTHFORGE AI is ready → {APP_URL}", "ok")
        webbrowser.open(APP_URL)   # auto-open browser

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _set_status(self, text: str, colour: str):
        self._status_var.set(text)
        self._led.itemconfig(self._led_oval, fill=colour)

    def _log_line(self, text: str, tag: str = "info"):
        """Thread-safe log append."""
        def _write():
            self._log.configure(state="normal")
            self._log.insert("end", text + "\n", tag)
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _write)

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _open_browser(self):
        if self._ready:
            webbrowser.open(APP_URL)
        else:
            messagebox.showinfo(
                "Server Not Running",
                "Start the server first, then click Open Browser."
            )

    def _on_close(self):
        if self._proc and self._proc.poll() is None:
            if messagebox.askyesno(
                "Quit TRUTHFORGE AI",
                "The server is still running.\nStop it and quit?"
            ):
                self._stop_server()
                self.destroy()
        else:
            self.destroy()


# ── Widget helpers ────────────────────────────────────────────────────────────

def _make_btn(parent, text, bg, fg, command=None, state="normal"):
    btn = tk.Button(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        activebackground=bg,
        activeforeground=fg,
        font=("Helvetica", 10, "bold"),
        relief="flat",
        bd=0,
        padx=14,
        pady=10,
        cursor="hand2",
        command=command,
        state=state,
    )
    # Hover effect
    def _on_enter(e):
        if btn["state"] == "normal":
            btn.configure(bg=_lighten(bg))
    def _on_leave(e):
        btn.configure(bg=bg)
    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return btn


def _rounded_border(frame):
    """Add a subtle border via a 1-px frame wrapper."""
    frame.configure(highlightbackground=BORDER, highlightthickness=1)


def _lighten(hex_colour: str, amount: int = 20) -> str:
    """Return a slightly lighter version of a hex colour."""
    try:
        r = int(hex_colour[1:3], 16) + amount
        g = int(hex_colour[3:5], 16) + amount
        b = int(hex_colour[5:7], 16) + amount
        return "#{:02x}{:02x}{:02x}".format(
            min(r, 255), min(g, 255), min(b, 255)
        )
    except Exception:
        return hex_colour


# Tiny 16×16 scales-of-justice icon (base64 PNG, optional — silently skipped)
_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABmJLR0QA/wD/AP+gvaeTAAAA"
    "AAAASUVORK5CYII="
)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)    # ensure CWD is project root
    app = TruthforgeLauncher()
    app.mainloop()
