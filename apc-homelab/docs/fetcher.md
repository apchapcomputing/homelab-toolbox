# Fetcher

A small service in the brain pod. n8n gives it a URL, and it returns a raw clipping note. n8n never handles audio and never runs a shell.

```
n8n --POST /fetch {"url": ...}--> fetcher --yt-dlp--> site
                                     │   captions? ──yes──► note
                                     └── no: download audio ──► Whisper (127.0.0.1:8000) ──► note
```

It listens on `127.0.0.1:8080` inside the pod. The pod publishes only n8n's port, so nothing outside the pod can reach it. Jobs run one at a time, because Whisper on a CPU is the bottleneck.

## API

`POST /fetch` with `{"url": "https://...", "medium": "podcast"}` (`medium` is optional).

Success, `200`:

| Field | Meaning |
|---|---|
| `filename` | Safe to use as the inbox filename: letters, digits, space `. _ ( ) -` only, which is what `brain-run` accepts |
| `note` | The whole markdown file, in the clipping format from the vault's `Input/CLAUDE.md`, with an empty `summary:` for Claude Code to fill |
| `transcript` | `captions`, `auto-captions` or `whisper`. Also written into the note's frontmatter |
| `title`, `medium`, `duration_s`, `chars` | For logging and for the Todoist comment |

Errors return `{"error": "..."}`: `400` bad request, `409` the same URL is already being fetched, `422` refused (private address, too long), `502` the site or Whisper failed, `504` timed out. n8n should leave the Todoist task open on any of them, so the next poll retries.

`GET /healthz` returns `{"ok": true}`.

## What it does and refuses

- Manual English captions first, then auto-captions, then Whisper on the audio. Set `ACCEPT_AUTO_CAPTIONS=0` to skip auto-captions when you would rather have Whisper's text.
- Only `http` and `https`. It refuses any address that resolves to this machine or a private network. It checks the name once and does not defend against DNS rebinding.
- Over `MAX_DURATION_S` (4 hours) or `MAX_AUDIO_MB` (250) it gives up.
- `medium` is `video` or `podcast`, guessed from the file. The Todoist link does not say which, so pass `medium` or correct the note by hand.

## Configuration

Environment variables in `fetcher.container.j2`: `WHISPER_URL`, `WHISPER_MODEL` (from `whisper_model` in `group_vars/all.yml`), `MAX_DURATION_S`, `MAX_AUDIO_MB`, `ACCEPT_AUTO_CAPTIONS`.

The image is built on the server by Quadlet (`fetcher.build`). Its tag is derived from `ytdlp_version` and the code, so editing either rebuilds it on the next run. yt-dlp needs updating every few weeks when YouTube changes: bump `ytdlp_version`, re-run `--tags pipeline`.

The container runs as a non-root user with a read-only filesystem, no capabilities, and `/tmp` in memory.

## How it was tested, and what was not

Tested on a laptop with a stand-in for Whisper:
- Captions path against a public YouTube video, including the exact note output.
- Whisper path against a direct audio file: the multipart upload carried the `model` and `file` fields and the text came back.
- Refusals: `127.0.0.1`, `169.254.169.254`, `file://`. A duplicate request got `409`.
- The image builds, and with the Quadlet's restrictions a real fetch succeeds inside it.
- Podman's Quadlet generator accepts every unit file.

Not tested:
- **Real Whisper.** The speaches model route, speed on this CPU, and a long episode. Expect a one-hour podcast to take a while.
- **Podcast pages.** Direct audio links work. Apple Podcasts and Spotify episode pages may not be supported by yt-dlp. Try your real links before relying on them.
- **YouTube from the server.** It worked from the test machine. A server IP can get "confirm you are not a bot" blocks. If that happens, yt-dlp needs cookies, which means a credential in the pipeline user's account.
- The n8n side. There is no workflow yet.
