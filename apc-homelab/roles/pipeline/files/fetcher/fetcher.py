#!/usr/bin/env python3
"""Fetcher: a URL goes in, a raw clipping note comes out.

Runs in the brain pod next to n8n and Whisper. n8n calls POST /fetch with {"url": ...}
and writes the returned note into the inbox, so n8n never handles audio or runs a shell.

Transcript order: captions from the site, then Whisper on the downloaded audio.
The note matches the clipping format in the vault's Input/CLAUDE.md, with an empty
summary for Claude Code to fill in.
"""
import html
import http.client
import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BIND = os.environ.get("BIND", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
WHISPER_URL = os.environ.get("WHISPER_URL", "http://127.0.0.1:8000")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "Systran/faster-whisper-small")
MAX_DURATION_S = int(os.environ.get("MAX_DURATION_S", str(4 * 3600)))
MAX_AUDIO_MB = int(os.environ.get("MAX_AUDIO_MB", "250"))
ACCEPT_AUTO_CAPTIONS = os.environ.get("ACCEPT_AUTO_CAPTIONS", "1") != "0"
AUDIO_EXTS = {"mp3", "m4a", "aac", "ogg", "oga", "opus", "wav", "flac"}
YTDLP_EXTRA = os.environ.get("YTDLP_EXTRA", "--js-runtimes node").split()
WHISPER_TIMEOUT_S = int(os.environ.get("WHISPER_TIMEOUT_S", str(4 * 3600)))

# One job at a time: Whisper on CPU is the bottleneck and two at once only slow both.
_job_lock = threading.Lock()
_inflight = set()
_inflight_guard = threading.Lock()


class FetchError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def check_url(url):
    """http(s) only, and nothing that resolves to this machine or the local network."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError(400, "only http and https URLs are accepted")
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(parts.hostname, None)}
    except socket.gaierror as exc:
        raise FetchError(422, f"cannot resolve {parts.hostname}: {exc}")
    for addr in addrs:
        ip = ipaddress.ip_address(addr.split("%")[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise FetchError(422, "that address points at a private network")


def ytdlp(args, timeout):
    cmd = ["yt-dlp", "--no-playlist", "--no-cache-dir", "--no-warnings", *YTDLP_EXTRA, *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True)
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or "").strip().splitlines()[-1:] or ["yt-dlp failed"]
        raise FetchError(502, tail[0][:300])
    except subprocess.TimeoutExpired:
        raise FetchError(504, "yt-dlp timed out")


def vtt_to_text(vtt):
    out, prev = [], None
    for line in vtt.splitlines():
        line = line.strip()
        if (not line or line.isdigit() or "-->" in line
                or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))):
            continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if line and line != prev:  # auto-captions repeat each line across cues
            out.append(line)
            prev = line
    return " ".join(out)


def paragraphs(text):
    """Break a wall of text into paragraphs, at a sentence end where there is one."""
    out, cur = [], []
    for word in text.split():
        cur.append(word)
        n = len(cur)
        if (n >= 90 and word[-1] in ".?!") or n >= 160:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return "\n\n".join(out)


def pick_track(tracks, order):
    """The one English track to download. Never a translated one such as en-de-DE."""
    return next((lang for lang in order if lang in (tracks or {})), None)


def get_captions(url, info, workdir):
    lang = pick_track(info.get("subtitles"), ("en", "en-US", "en-GB", "en-orig"))
    flag, kind = "--write-subs", "captions"
    if not lang and ACCEPT_AUTO_CAPTIONS:
        lang = pick_track(info.get("automatic_captions"), ("en-orig", "en", "en-US", "en-GB"))
        flag, kind = "--write-auto-subs", "auto-captions"
    if not lang:
        return None, None
    ytdlp(["--skip-download", flag, "--sub-langs", lang, "--sub-format", "vtt",
           "-o", str(workdir / "cap"), url], timeout=300)
    files = sorted(workdir.glob("cap*.vtt"))
    if not files:
        return None, None
    text = vtt_to_text(files[0].read_text(encoding="utf-8", errors="replace"))
    return (text, kind) if len(text) >= 200 else (None, None)


def get_audio(url, workdir):
    ytdlp(["-f", "bestaudio/worst", "--max-filesize", f"{MAX_AUDIO_MB}M",
           "-o", str(workdir / "audio.%(ext)s"), url], timeout=1800)
    files = [p for p in workdir.glob("audio.*") if p.suffix not in (".part", ".ytdl")]
    if not files:
        raise FetchError(502, "no audio was downloaded (file may be over the size limit)")
    return files[0]


def transcribe(path):
    """POST the audio to Whisper (speaches, OpenAI-compatible) as multipart/form-data."""
    boundary = "----fetcher" + os.urandom(8).hex()
    fields = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        for k, v in (("model", WHISPER_MODEL), ("response_format", "json")))
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    length = len(fields) + len(head) + path.stat().st_size + len(tail)

    def body():
        yield fields + head
        with path.open("rb") as fh:
            while chunk := fh.read(1 << 20):
                yield chunk
        yield tail

    target = urllib.parse.urlsplit(WHISPER_URL)
    conn = http.client.HTTPConnection(target.hostname, target.port or 80, timeout=WHISPER_TIMEOUT_S)
    try:
        conn.request("POST", "/v1/audio/transcriptions", body=body(), headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(length)})
        resp = conn.getresponse()
        data = resp.read()
    except (OSError, http.client.HTTPException) as exc:
        raise FetchError(502, f"Whisper is not reachable: {exc}")
    finally:
        conn.close()
    if resp.status != 200:
        raise FetchError(502, f"Whisper returned {resp.status}: {data[:200].decode(errors='replace')}")
    return json.loads(data)["text"].strip()


def clean_filename(title, fallback):
    """Keep only characters that brain-run accepts: letters, digits, space . _ ( ) -"""
    name = re.sub(r"[^A-Za-z0-9._() -]+", " ", title)
    name = re.sub(r"\s+", " ", name).strip(" .-_")[:120].strip()
    return (name or fallback) + ".md"


def clean_link_text(text):
    return re.sub(r"[\[\]|#^:?*<>/\\\"]+", "", text).strip()


def q(value):
    return json.dumps(value, ensure_ascii=False)


def build_note(info, url, medium, kind, text):
    channel = clean_link_text(info.get("channel") or info.get("uploader") or "")
    upload = info.get("upload_date") or ""
    published = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else ""
    description = " ".join((info.get("description") or "").split())[:200]
    lines = ["---", f"title: {q(info.get('title') or 'Untitled')}", f"source: {q(url)}"]
    lines += ["author:", f'  - {q("[[" + channel + "]]")}'] if channel else ["author:"]
    lines += [f"published: {published}", f"created: {date.today().isoformat()}",
              f"description: {q(description)}", "summary:", f"medium: {medium}",
              f"transcript: {kind}", "tags: []", "---", "", "## Transcript", "", paragraphs(text), ""]
    return "\n".join(lines)


def fetch(url, medium_override=None):
    check_url(url)
    with tempfile.TemporaryDirectory(prefix="fetch-") as tmp:
        workdir = Path(tmp)
        info = json.loads(ytdlp(["--skip-download", "--dump-single-json", url], timeout=120).stdout)
        if (info.get("duration") or 0) > MAX_DURATION_S:
            raise FetchError(422, f"longer than the {MAX_DURATION_S // 3600} hour limit")
        text, kind = get_captions(url, info, workdir)
        if not text:
            text, kind = transcribe(get_audio(url, workdir)), "whisper"
        if not text:
            raise FetchError(502, "the transcript came back empty")
    vcodec = info.get("vcodec")
    audio_only = vcodec == "none" or (vcodec is None and info.get("ext") in AUDIO_EXTS)
    medium = medium_override or ("podcast" if audio_only else "video")
    return {
        "filename": clean_filename(info.get("title") or "", info.get("id") or "clipping"),
        "note": build_note(info, url, medium, kind, text),
        "title": info.get("title"),
        "medium": medium,
        "transcript": kind,
        "duration_s": info.get("duration"),
        "chars": len(text),
    }


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            self.reply(200, {"ok": True})
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/fetch":
            return self.reply(404, {"error": "not found"})
        try:
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= 65536:
                raise FetchError(400, "send a small JSON body")
            req = json.loads(self.rfile.read(size))
            url = str(req.get("url", "")).strip()
            if not url:
                raise FetchError(400, "url is required")
            with _inflight_guard:
                if url in _inflight:
                    raise FetchError(409, "that URL is already being fetched")
                _inflight.add(url)
            try:
                with _job_lock:
                    print(f"fetch start: {url}", flush=True)
                    result = fetch(url, req.get("medium"))
                    print(f"fetch done: {result['transcript']} {result['chars']} chars", flush=True)
            finally:
                with _inflight_guard:
                    _inflight.discard(url)
            self.reply(200, result)
        except FetchError as exc:
            print(f"fetch failed ({exc.status}): {exc}", flush=True)
            self.reply(exc.status, {"error": str(exc)})
        except (ValueError, KeyError) as exc:
            self.reply(400, {"error": f"bad request: {exc}"})
        except Exception as exc:  # keep the server alive whatever a site throws at yt-dlp
            print(f"fetch crashed: {exc!r}", flush=True)
            self.reply(500, {"error": "internal error"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"fetcher listening on {BIND}:{PORT}", flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
