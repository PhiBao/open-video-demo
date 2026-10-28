"""Shared helpers for the demo-video pipeline.

One template, many video projects. Every project lives in its own folder
(`videos/<name>/`) and contains:

    script/story.json     the narration + scene definitions
    config/video.json     resolution, voice, subtitles, branding
    assets/               optional per-project overrides of template assets
    audio/ clips/ build/ work/ qa/ out/     generated

The template itself (scripts/, assets/, defaults/) is shared and never
modified by a render. A project is resolved from, in order:

    1. `--project <name|path>` on any script or run.sh
    2. the DEMO_DIR environment variable
    3. the current directory (or an ancestor) if it is a project
    4. videos/<name> when exactly one project exists
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path(os.environ.get("DEMO_TEMPLATE") or Path(__file__).resolve().parent.parent)
VIDEOS = TEMPLATE / "videos"

# filled in by init()
ROOT = CONFIG = STORY = BUILD = AUDIO = CLIPS = WORK = QA = OUT = None

DEFAULTS = {
    "name": "demo",
    "output": "out/demo.mp4",
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "voice": "en-US-GuyNeural",
    "rate": "-4%",
    "volume": "+0%",
    "pad": 0.45,
    "trim": 0.6,
    "crf": 20,
    "preset": "medium",
    "burn_subtitles": True,
    "loudness": "I=-16:TP=-1.5:LRA=11",
    "subtitle_style": (
        "FontName=DejaVu Sans,FontSize=30,PrimaryColour=&HFFFFFF,"
        "OutlineColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,"
        "MarginV=46,PlayResX=1920,PlayResY=1080"
    ),
    "branding": {},
    "theme": {},
}

# Every {{placeholder}} a card template may use for colors. Projects override
# any subset via config/video.json "theme". Scene "vars" override per scene.
THEME_DEFAULTS = {
    "bg": "#06070b",
    "accent1": "#34d399",
    "accent2": "#22d3ee",
    "accent3": "#a78bfa",
    "ink": "#e8e8f0",
    "muted": "#9aa2bd",
    "faint": "#6f7794",
    "subc": "#5eead4",
    "hi": "#f87171",
    "hi2": "#34d399",
    "shade": "rgba(0,0,0,.30)",
}


def find_projects():
    if not VIDEOS.exists():
        return []
    return sorted(p.parent.parent for p in VIDEOS.glob("*/script/story.json"))


def resolve_root(project=None):
    candidates = []
    if project:
        p = Path(project)
        if p.is_absolute():
            candidates.append(p)
        else:
            candidates += [VIDEOS / p, TEMPLATE / p, Path.cwd() / p]
        candidates = [c.parent.parent if c.name == "story.json" else c
                      for c in candidates]
    elif os.environ.get("DEMO_DIR"):
        candidates.append(Path(os.environ["DEMO_DIR"]).expanduser())
    else:
        here = Path.cwd().resolve()
        candidates += [here, *here.parents]
        candidates += find_projects()
    for c in candidates:
        if (c / "script" / "story.json").exists():
            return c.resolve()
    known = find_projects()
    if not known:
        sys.exit("no project found - create one with ./scripts/new.sh <name>")
    sys.exit("could not pick a project; pass --project <name>. known: "
             + ", ".join(p.name for p in known))


def init(project=None):
    """Resolve the project and bind module path globals. Call from main()."""
    global ROOT, CONFIG, STORY, BUILD, AUDIO, CLIPS, WORK, QA, OUT
    ROOT = resolve_root(project)
    CONFIG = ROOT / "config" / "video.json"
    STORY = ROOT / "script" / "story.json"
    BUILD = ROOT / "build"
    AUDIO = ROOT / "audio"
    CLIPS = ROOT / "clips"
    WORK = ROOT / "work"
    QA = ROOT / "qa"
    OUT = ROOT / "out"
    return ROOT


def project_label():
    try:
        return str(ROOT.relative_to(TEMPLATE))
    except ValueError:
        return str(ROOT)


def project_arg(parser):
    parser.add_argument("--project", metavar="NAME",
                        help="video project under videos/ (or a path)")


def asset(rel):
    """Project asset if present, else the shared template asset.

    Project overrides live in videos/<name>/assets/<rel> (e.g.
    videos/acme/assets/cards/title.html). The bare ROOT/<rel> path is
    checked second for backward compatibility.
    """
    for p in (ROOT / "assets" / rel, ROOT / rel):
        if p.exists():
            return p
    return TEMPLATE / "assets" / rel


def ensure_dirs():
    for d in (BUILD, AUDIO, CLIPS, WORK, QA, OUT):
        d.mkdir(parents=True, exist_ok=True)


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(load_json(CONFIG))
    cfg["branding"] = {**DEFAULTS["branding"], **cfg.get("branding", {})}
    cfg["theme"] = {**THEME_DEFAULTS, **cfg.get("theme", {})}
    return cfg


def load_story():
    if not STORY.exists():
        sys.exit(f"missing {STORY} - write the script first (see AGENTS.md)")
    story = load_json(STORY)
    segs = story.get("segments") or []
    if not segs:
        sys.exit(f"{STORY} has no segments")
    seen = set()
    for s in segs:
        if not s.get("id") or not s.get("text"):
            sys.exit(f"{STORY}: every segment needs 'id' and 'text'")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", s["id"]):
            sys.exit(f"{STORY}: id {s['id']!r} must be a slug "
                     "(letters, digits, _ or -)")
        if s["id"] in seen:
            sys.exit(f"{STORY}: duplicate segment id {s['id']!r}")
        seen.add(s["id"])
    return story


def load_segments():
    path = BUILD / "segments.json"
    if not path.exists():
        sys.exit("missing build/segments.json - run scripts/tts.py first")
    return load_json(path)


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def run(cmd, timeout=None, cwd=None):
    r = subprocess.run(
        [str(c) for c in cmd], capture_output=True, text=True,
        timeout=timeout, cwd=str(cwd or ROOT),
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"command failed ({r.returncode}): {' '.join(str(c) for c in cmd[:10])}\n"
            f"{r.stderr[-3000:]}"
        )
    return r.stdout


def edge_tts_bin():
    local = Path(sys.executable).parent / "edge-tts"
    if local.exists():
        return str(local)
    found = shutil.which("edge-tts")
    if not found:
        sys.exit("edge-tts not found - run ./scripts/setup.sh")
    return found


def chromium_bin():
    """Prefer an explicit path, then a system chromium, else Playwright's bundle."""
    for cand in (os.environ.get("CHROMIUM_PATH"), shutil.which("chromium"),
                 shutil.which("chromium-browser"), shutil.which("google-chrome"),
                 shutil.which("google-chrome-stable")):
        if cand and Path(cand).exists():
            return cand
    return None


def ffprobe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=0", path])
    return round(float(out.strip().split("=")[1]), 3)


def ffprobe_json(path):
    out = run(["ffprobe", "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", path])
    return json.loads(out)


TS_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def _secs(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(path):
    """SRT -> [(start, end, text)]."""
    text = Path(path).read_text(errors="replace").strip()
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        m = TS_RE.search(lines[1])
        if not m:
            continue
        g = m.groups()
        cues.append((_secs(*g[:4]), _secs(*g[4:]), "\n".join(lines[2:]).strip()))
    return cues


def fmt_ts(x):
    x = max(0.0, x)
    return (f"{int(x // 3600):02}:{int(x % 3600 // 60):02}:{int(x % 60):02},"
            f"{int(x % 1 * 1000):03}")


def write_srt(cues, path, width=70, max_lines=2):
    with open(path, "w") as f:
        for i, (a, b, txt) in enumerate(cues, 1):
            words, lines, cur = txt.replace("\n", " ").split(), [], ""
            for w in words:
                if cur and len(cur) + len(w) + 1 > width:
                    lines.append(cur)
                    cur = w
                else:
                    cur = (cur + " " + w).strip()
            if cur:
                lines.append(cur)
            f.write(f"{i}\n{fmt_ts(a)} --> {fmt_ts(b)}\n"
                    + "\n".join(lines[:max_lines]) + "\n\n")
    return len(cues)
