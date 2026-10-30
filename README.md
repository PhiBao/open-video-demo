# open-video-demo

Turn a repository into a narrated, subtitled 1080p demo video with one command.
Built for hackathon submissions: no timeline editor, no API keys, no cloud
rendering service. Playwright records HTML scenes, `edge-tts` narrates,
`ffmpeg` assembles.

The template is **one toolkit, many videos**: every video is a folder under
`videos/`, with its own script, branding, and generated artifacts.

```bash
./scripts/setup.sh                    # once: venv + playwright + browser check
./scripts/new.sh acme-demo            # scaffold videos/acme-demo/
$EDITOR videos/acme-demo/script/story.json     # the script + the scenes
$EDITOR videos/acme-demo/config/video.json     # branding (names, tagline, links)
./scripts/run.sh --project acme-demo           # tts -> record -> build -> qa
xdg-open videos/acme-demo/out/acme-demo.mp4
```

Run it on the bundled example first to see the full loop:

```bash
./scripts/run.sh --project example
```

Then open `videos/example/qa/contact_sheet.jpg` and `qa/report.txt` and
iterate with `./scripts/run.sh --project example --only <scene_id>`.

`--project` accepts a name under `videos/` or a path; it can be omitted when
you are inside the project folder or only one project exists.

## Why it is fast to iterate

- **Audio is fingerprinted.** Edit a segment's text and only its narration
  regenerates; everything else is cached.
- **Clips are fingerprinted.** Edit a scene - or the HTML page it shows - and
  only that clip re-records.
- **Timing is automatic.** Each scene is recorded for exactly
  `lead-in + narration + slack`, then trimmed and freeze-padded to fit the
  audio. You never hand-tune durations.
- **Subtitles are free.** edge-tts emits real word timings; `build.py` shifts
  and burns them, and writes a sidecar `.srt` for uploads.

## Scene kinds

| kind | What it is | Use it for |
|---|---|---|
| `card` | animated HTML title/close card | hook and close |
| `term` | synthetic terminal replaying scripted lines | CLI output, benchmarks, test results |
| `page` | live or local web page with scripted scroll/click/type | showing the actual product |

Scenes are JSON in `script/story.json` - see [AGENTS.md](AGENTS.md) for the
full reference. `videos/example/app/index.html` is a placeholder product page
so the example runs end to end out of the box.

## Crypto demos

A connect popup is screen time spent on the wallet instead of the product, so
crypto demos use an injected wallet by default: a test key from
`wallets/.env` is already connected when the page loads, and signatures are
real. Set `"wallet": "inject"` on a scene (or on the video in
`config/video.json`). Reads go through `EVM_RPC_URL`; transactions are only
broadcast when `WALLET_BROADCAST=1`.

```bash
cp wallets/.env.example wallets/.env
./scripts/setup.sh --wallet
.venv/bin/python scripts/wallet_inject_check.py
```

The MetaMask profile (`"wallet": "metamask"`) is still available when the
approval flow itself is what the demo is about. Details in
[wallets/README.md](wallets/README.md).

## Layout

```
AGENTS.md              playbook for a coding agent (start here)
defaults/video.json    config copied by scripts/new.sh
scripts/               new.sh, run.sh, tts.py, record.py, build.py, qa.py, setup.sh
assets/cards/*.html    shared card templates with {{placeholders}}
assets/themes/*.css    shared terminal theme
wallets/               test keys, injected wallet, optional MetaMask profile
videos/example/        the only project committed; others stay local
videos/<name>/
  script/story.json    the script + scene definitions
  config/video.json    resolution, voice, subtitles, branding
  assets/              optional per-project overrides of template assets
  audio/ clips/ build/ work/ qa/   generated, cached
  out/<name>.mp4       the finished video (+ .srt)
```

## Commands

```bash
./scripts/new.sh <name>                                  # scaffold a project
./scripts/run.sh [--project NAME] [--only id...] [--force]
                 [--no-tts|--no-record|--no-build|--no-qa]
make setup | list | new NAME=x | all PROJECT=x | tts | record | build | qa
```

`DEMO_DIR` points at a project via environment; `CHROMIUM_PATH` overrides the
browser.

## Requirements

`ffmpeg` + `ffprobe`, Python 3.9+, and `edge-tts` (installed into `.venv`).
A system chromium is used when present, otherwise `playwright install chromium`
downloads one. Narration needs network access to Microsoft's TTS endpoint.

Scenes are captured in real time rather than re-implemented in a video
framework, so the `page` scene always shows the actual product.

## What is not in this repo

Generated artifacts (`audio/`, `clips/`, `build/`, `work/`, `qa/`, `out/`),
the local `.venv`, and wallet state (`wallets/.env`, `wallets/profiles/`,
`wallets/extensions/`) are gitignored. Wallet profiles hold an encrypted
test wallet — never commit them, and never use a key or seed with real funds
(see `wallets/README.md`).

`videos/` is ignored except `videos/example/`, so per-project work stays
local by default. Publish one deliberately with
`git add -f videos/<name>`.

## License

MIT — see `LICENSE`.
