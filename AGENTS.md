# Agent playbook: repo -> product demo video

This folder is a **template**. Each video is its own project under `videos/`.
The target of every video is a **product demo**: show the product solving a
problem, with real proof - never a scene checklist.

```
videos/<name>/
├── script/story.json     the script + scene definitions   (you write this)
├── config/video.json     branding, voice, subtitles       (you edit this)
├── assets/               optional per-project asset overrides
└── audio/ clips/ build/ work/ qa/ out/                    (generated)
```

The template's `scripts/` and `assets/` are shared and never modified by a
render. Start by creating a project:

```bash
./scripts/new.sh acme-demo          # scaffold videos/acme-demo/
# write videos/acme-demo/script/story.json
# edit  videos/acme-demo/config/video.json
./scripts/run.sh --project acme-demo
```

Then read `qa/report.txt` and **look at** `qa/contact_sheet.jpg` +
`qa/frames/*.jpg` (use the Read tool on images). Iterate until the video is
right. Never stop at "the command exited 0" - inspect the frames.

`--project` accepts a name under `videos/` or a path. It can be omitted when
you are inside the project folder or when only one project exists. `DEMO_DIR`
does the same via environment.

## Source vs generated

| Write | Never hand-edit |
|---|---|
| `videos/<name>/script/story.json` | `audio/`, `clips/`, `build/`, `work/` |
| `videos/<name>/config/video.json` | `qa/`, `out/` |
| `videos/<name>/assets/` (overrides) | |
| template `assets/` (cards, themes) | |

## Workflow

### 1. Recon (no writing yet)

- Read the project README/docs to find the 2-4 things that are genuinely
  impressive: a live URL, a measurable number, a transaction hash, a result.
- Identify the product's main surface first - it decides the scene mix:
  a web app (live URL or local dev server), a CLI tool with real output, or
  an API/agent with real request -> response behavior.
- Web app: start it (or use `file://`). Note stable selectors for the page
  scene (`.stats`, `#search`, `text=...`) and walk the flows the demo needs.
- CLI/API: collect **verbatim** material by running the real commands and
  copying the real output (abbreviate long hashes with `...`).

If you cannot verify a fact, do not put it in the video.

### 2. Write the story - it is a product demo

Structure that works for product demos. Length follows the product, not a
quota - roughly **60-180s**: a focused CLI flow may be done in a minute, a
rich web app may need three. Use the shortest cut that shows the product
working and proves it; stop there. The spine is the same for every
product; what changes is which surface carries it:

| # | Role | Content |
|---|---|---|
| 1 | Hook | one-sentence framing; title card |
| 2 | Problem | the gap, with real measured numbers |
| 3 | Product | the actual product surface, working - the hero of the video |
| 4-7 | Proof | real results: live app state, a fill, a signed receipt, test output - at least two distinct proofs |
| last | Close | one-line thesis + links; close card |

**Pick scenes to fit the product** - the scene kind is a fact about the
product, not a template ritual:

| product | demo scenes | terminal scenes |
|---|---|---|
| web app / SaaS / dashboard | `page` - the demo lives here: more screen time, more interaction, go deeper into the real app | only for real CLI/API output (a deploy, a test run) as support |
| CLI / dev tool / infra | `term` with real commands and their copied output - the terminal IS the product | the whole demo |
| API / agent / protocol | `page` console if one exists; `term` for request -> result proof | request/response proof |

Never insert a terminal scene because "these videos always have one". If
the product has no terminal, a `term` scene invents a surface that does not
exist - use `page` (or a card) instead. The reverse holds too: a CLI
product shown only through a web screenshot hides the actual demo.

Duration rules:

- Speech is ~2.5 words/second (voice/rate in config). A 40-word segment ≈ 16s.
- **Total: roughly 60-180s, i.e. ~150-450 words of narration** - let the
  product decide. There is no hard gate; `qa.py` only reports duration.
  Judge it by content: if the product is shown working and proved, it is
  long enough, whether that took sixty seconds or three minutes.
- 4-10 segments, most 8-30s each. **Every second must show something new.**
- Too thin (product barely shown, proof missing): add depth - a second
  proof, a deeper product pass, the failure case - never pad a card or
  slow a scene to hit a number. Dragging: cut a segment or tighten
  narration; keep hook/product/proof/close.
- Speak numbers as words (`forty cents`, not `$0.40`). Spell URLs/domains
  (`okx dot A I`). No emoji, no markdown, no stage directions.
- Do not read terminal text verbatim - narration adds meaning, the screen
  shows detail. Keep them in sync: say what appears, when it appears.

Target the **visual** to the narration at the midpoint of each segment; that
is the frame QA shows you.

### 3. Configure branding (do NOT keep the default intro)

`config/video.json` `branding` fills the `{{placeholders}}` in card templates:
`name` (big title), `tagline`, `sub`, `note`, `meta` (title card);
`name`, `headline` (may contain `<b>`/`<i>`), `links`, `footnote` (close card).
Override per scene with `"vars": {...}`.

Pick the intro layout that fits the product, then recolor it via the
`theme` block (`bg`, `accent1/2/3`, `ink`, `muted`, `faint`, `subc`,
`hi`, `hi2`, `shade`). Scene `vars` override theme keys per scene,
and `{{kicker}}` falls back to `{{meta}}`:

| template pair | feel | use for |
|---|---|---|
| `title` / `close` | centered, confident | infra / autopilot brands |
| `title-left` / `close-left` | editorial rail + kicker, investigative | devtools, data-truth products |
| `title-soft` / `close-soft` | light calm card, serif | human / clinical / voice products |

```json
{"kind": "card", "template": "title-left",
 "vars": {"kicker": "FRIDAY 4PM &middot; THE BELL RINGS"}}
```

Cards render solid ink type with one accent (the rule, the dot, the
tagline), a fast staggered entrance that settles ~1.5s in, then hold
still for the narration. Restyles should stay restrained: no gradient
text fills, no glow blobs behind the heading - depth comes from the
`shade` vignette and spacing.

Changing `theme`, `branding`, or scene `vars` forces that card to
re-record. A per-project override at
`videos/<name>/assets/cards/<template>.html` wins over the shared template;
copy a shared file there and restyle it, keeping `{{placeholder}}` names.

### 4. Run and iterate

```bash
./scripts/run.sh --project acme-demo
./scripts/run.sh --project acme-demo --only s3_app   # re-record one scene
./scripts/run.sh --project acme-demo --force         # regenerate audio+clips
./scripts/run.sh --project acme-demo --no-record     # rebuild only
```

Change narration -> audio regenerates automatically (text is fingerprinted).
Change a scene -> that clip re-records automatically. Editing a local page
(`src: "app/index.html"`) also triggers a re-record.

### 5. QA - the part that matters

1. `qa/report.txt` - duration, streams, loudness, black gaps, short clips.
2. `qa/contact_sheet.jpg` - 16 frames across the video. Every tile must show
   content; no blank/frozen/duplicated scenes.
3. `qa/frames/<id>.jpg` - mid-segment frame per scene; check that the visual
   matches what the narration says at that moment.
4. Fix and re-run with `--only`. Repeat until `PASS`.

## Scene reference (`script/story.json`)

Each segment: `{ "id", "text", "scene": {...} }`.

### `card` - animated HTML card
```json
{"kind":"card","template":"title","vars":{"meta":"optional overrides"}}
```
Templates: template `assets/cards/title.html`, `close.html`, overridable with
`videos/<name>/assets/cards/*.html`. Edit the HTML to restyle; keep
`{{placeholder}}` names in sync with `branding`.

### `term` - synthetic terminal replay
```json
{"kind":"term","title":"app - deployment","lines":[
  {"at":0.4,"type":"cmd","text":"make deploy","cps":16},
  {"at":2.0,"text":"staging ... ok","cls":"dim"},
  {"at":4.0,"text":"verdict  PASS","cls":"green","flash":"g"}
]}
```
- `at` seconds from scene start; `type`: `cmd` (typewriter), `rule`, `gap`, or
  omit for instant line.
- `cls`: `p dim red amb vio green white cy`; `flash`: `red` or `g`.
- **Last line should land ~2s before the segment ends.**

### `page` - live/local page with a scripted pass
```json
{"kind":"page","src":"http://localhost:3000","zoom":1.5,
 "wait_for":["text=Dashboard"],"settle":1.0,
 "actions":[
   {"action":"move","x":0.5,"y":0.15,"dur":0.7},
   {"action":"scrollTo","sel":".stats","dur":1.2,"after":0.6},
   {"action":"click","sel":"#cta","after":0.4},
   {"action":"type","sel":"#search","text":"hello","cps":16},
   {"action":"wait","sec":1.0}
 ]}
```
- `src`: http(s) URL, or a path relative to the project (then the template).
- `zoom` scales small apps up for legibility (1.5-1.7 typical).
- Actions: `move` (x/y are 0-1 viewport fractions), `scrollTo` (`sel` or
  `y` fraction; `at` = where on screen the element lands), `click`, `hover`,
  `type`, `press`, `wait`, `zoom`. `after` = pause after the action;
  `dur` = animation length.
- Keep the action timeline shorter than the narration; the recorder measures
  its own lead-in automatically.
- Selector misses are printed as warnings - always check them.

### Crypto demos - wallet connect / sign / transaction

When a demo needs a real wallet signature, use the local MetaMask profile.
It covers EVM and Solana accounts from one seed. Setup and troubleshooting
live in `wallets/README.md`.

```bash
.venv/bin/python scripts/wallet_lib.py setup metamask   # one-time seed import
.venv/bin/python scripts/wallet_verify.py               # connect + sign check
```

Enable it for a whole demo in `config/video.json`:

```json
{"wallet": "metamask"}
```

or per scene with `"wallet": "metamask"` / `"crypto": true`. The recorder
launches the persistent profile, unlocks it with the local password
(`123123123`), and keeps one wallet tab plus the dapp page.

Approve wallet prompts with recorder actions, not by hand:

```json
{"kind":"page","src":"https://dapp.example","wallet":"metamask","chain":"evm",
 "actions":[
   {"action":"click","sel":"text=Connect"},
   {"action":"wallet_approve","kind":"connect","after":1.0},
   {"action":"click","sel":"text=Sign"},
   {"action":"wallet_approve","kind":"sign","after":1.0},
   {"action":"click","sel":"text=Send"},
   {"action":"wallet_approve","kind":"transaction","after":2.0}
 ]}
```

- `wallet_approve` opens the extension's `notification.html` and clicks the
  pending Connect / Sign / Confirm button. It does not depend on a popup
  window (MetaMask's side panel is invisible to Playwright).
- `kind`: `connect`, `sign`, `transaction`.
- `chain`: `evm` or `solana` (documentation; the approval helper is tolerant).
- Solana dapps use Wallet Standard / MetaMask Connect; when they open a
  MetaMask request, the same `wallet_approve` action handles it.
- The wallet notification tab is not part of the main page recording. If the
  wallet UI must be on camera, record that tab separately and composite it.

## Timing model (why things fit)

`tts.py` measures each narration; `record.py` records `trim + dur + slack`;
`build.py` trims the lead-in, pads/freezes to exactly `dur + pad`, muxes audio,
concats, burns subtitles from edge-tts word timings, normalizes to -16 LUFS.
To change timing, change the **text** or move line `at` values - never edit
generated files.

## Common failures

| Symptom | Fix |
|---|---|
| `edge-tts failed ... 3 attempts` | network blocked; retry or change `voice`/`rate` |
| `chromium` missing | `./scripts/setup.sh` |
| `selector ... not found` | check the real DOM; add as `wait_for`; app not loaded |
| `clip ... < needed` QA warning | scene/actions ran past narration; shorten `after`/`dur` or lengthen text |
| unresolved card placeholders | add the key to `branding` or scene `vars` |
| subtitles wrap past 2 lines | shorten the sentence in `text` |
| video too thin / dragging | thin: add a proof / deeper product pass (never pad); dragging: cut a segment; keep hook/product/proof/close |
| video feels like a scene checklist | product scenes too thin; give `page` the screen time; drop `term` when the product has no terminal |
| `no project found` | `./scripts/new.sh <name>` then `--project <name>` |

## Definition of done

- [ ] the file at `videos/<name>/<output>` (config `output`, default
      `out/demo.mp4`) plays start to finish; audio present; 1920x1080.
- [ ] the product's real surface is the hero: `page` for apps, `term` only
      when the terminal is the product - no invented surfaces.
- [ ] `qa/report.txt` shows no warnings (or every warning is understood).
- [ ] Contact sheet: every frame has real content, matches its narration.
- [ ] Every number/hash/URL shown exists in the project (no invented facts).
- [ ] Duration fits the product (roughly 60-180s): product shown working
      and proved, with no padding and no missing proof.
