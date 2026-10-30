#!/usr/bin/env python3
"""Record every story segment as clips/<id>.webm with Playwright.

Scene kinds (see AGENTS.md for the full data format):
  card  - title/close HTML templates with {{placeholders}}
  term  - synthetic terminal replaying scripted lines with typewriter effects
  page  - a live or local web page with a scripted pass: cursor, scrolls,
          clicks, typing, zooms

Clip length is derived from the narration duration, so scenes always cover
their audio. Re-recording is skipped when the scene definition is unchanged;
use --force or --only <id>.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
import wallet_inject  # noqa: E402
import wallet_lib  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

TERMINAL_JS = r"""
const SPEC = __SPEC__;
const bodyEl = document.getElementById('body');
function addLine(html, cls) {
  const d = document.createElement('div');
  d.className = 'line' + (cls ? ' ' + cls : '');
  d.innerHTML = html;
  bodyEl.appendChild(d);
  bodyEl.scrollTop = bodyEl.scrollHeight;
  return d;
}
window.addEventListener('load', () => {
  document.body.classList.add('ready');
  SPEC.lines.forEach((l) => {
    setTimeout(() => {
      if (l.type === 'gap' || l.type === 'rule') {
        addLine(l.type === 'rule' ? '<span class="dim">' + '-'.repeat(66) + '</span>' : '&nbsp;');
        return;
      }
      if (l.type === 'cmd') {
        const d = addLine('<span class="p">$ </span><span class="cmdtext"></span><span class="cursor"></span>');
        const t = d.querySelector('.cmdtext');
        const cur = d.querySelector('.cursor');
        let j = 0;
        const iv = setInterval(() => {
          t.textContent = l.text.slice(0, ++j);
          if (j >= l.text.length) { clearInterval(iv); cur.remove(); }
        }, l.cps ? 1000 / l.cps : 34);
        return;
      }
      const d = addLine(l.text, l.cls);
      if (l.flash === 'red') {
        d.classList.add('flash');
        document.body.classList.add('flashred');
        setTimeout(() => document.body.classList.remove('flashred'), 1000);
      } else if (l.flash === 'g') {
        d.classList.add('flashg');
        document.body.classList.add('flashborder');
        setTimeout(() => document.body.classList.remove('flashborder'), 1000);
      }
    }, l.at * 1000);
  });
});
"""

PAGE_JS = r"""
() => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const tween = (dur, fn) => new Promise(res => {
    const t0 = performance.now();
    const step = (t) => { const p = Math.min(1, (t - t0) / (dur * 1000)); fn(p);
      if (p < 1) requestAnimationFrame(step); else res(); };
    requestAnimationFrame(step);
  });
  const ease = p => p < .5 ? 4*p*p*p : 1 - Math.pow(-2*p+2, 3)/2;
  const maxScroll = () => document.documentElement.scrollHeight - innerHeight;
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const elOf = (a) => {
    const sel = a.sel;
    // idx: pick the nth match, counting from the end for negative values
    // (a list of cards can each offer the same button; -1 is the last one).
    const pick = (hits) => {
      const i = a.idx == null ? 0 : a.idx;
      return (i < 0 ? hits[hits.length + i] : hits[i]) || null;
    };
    if (typeof sel === 'string' && (sel.startsWith('text=') || sel.startsWith('has='))) {
      const want = norm(sel.slice(sel.indexOf('=') + 1).replace(/^["']|["']$/g, ''));
      const all = [...document.querySelectorAll('button, a, option, li, p, h1, h2, h3, h4, code, span, td, th, label, div')];
      let hits = all.filter(el => {
        const t = sel.startsWith('has=') ? el.textContent : norm(el.textContent);
        return sel.startsWith('has=') ? (t || '').includes(want) : norm(t) === want || norm(t).includes(want);
      });
      // Keep the innermost matches: a click should target the button, not the
      // card that contains it.
      hits = hits.filter(el => !hits.some(other => other !== el && el.contains(other)));
      return pick(hits);
    }
    return pick([...document.querySelectorAll(sel)]);
  };
  const cur = () => document.getElementById('__cursor');
  async function cursorToXY(x, y, d) {
    const c = cur(); if (!c) return;
    const x0 = parseFloat(c.style.left || '50%'), y0 = parseFloat(c.style.top || '50%');
    await tween(d, p => { c.style.left = (x0 + (x - x0) * p) + 'px'; c.style.top = (y0 + (y - y0) * p) + 'px'; });
  }
  async function cursorToEl(el, d) {
    const r = el.getBoundingClientRect();
    await cursorToXY(r.left + r.width / 2, r.top + r.height / 2, d);
  }
  async function scrollToY(y, d) {
    const y0 = scrollY;
    await tween(d, p => scrollTo(0, y0 + (y - y0) * ease(p)));
  }
  window.__DEMO = {
    setup(zoom) {
      document.documentElement.style.zoom = String(zoom || 1);
      const st = document.createElement('style');
      st.textContent = `#__cursor{position:fixed;left:50%;top:50%;width:26px;height:26px;
        border-radius:50%;border:2.5px solid rgba(16,185,129,.95);
        background:rgba(16,185,129,.18);box-shadow:0 0 18px rgba(16,185,129,.5);
        pointer-events:none;z-index:2147483647}`;
      document.head.appendChild(st);
      const c = document.createElement('div'); c.id = '__cursor';
      c.style.left = (innerWidth / 2) + 'px';
      c.style.top = (innerHeight / 2) + 'px';
      document.body.appendChild(c);
      return true;
    },
    async run(a) {
      switch (a.action) {
        case 'wait':
          await sleep((a.sec == null ? 1 : a.sec) * 1000); return true;
        case 'move':
          await cursorToXY(innerWidth * a.x, innerHeight * a.y, a.dur || 0.8); return true;
        case 'zoom':
          document.documentElement.style.zoom = String(a.level || 1); return true;
        case 'scrollTo': {
          if (a.sel) {
            const el = elOf(a); if (!el) return false;
            await cursorToEl(el, a.dur || 0.7);
            const r = el.getBoundingClientRect();
            const at = a.at == null ? 0.26 : a.at;
            const y = Math.max(0, Math.min(r.top + scrollY - innerHeight * at, maxScroll()));
            await scrollToY(y, a.dur || 1.2);
          } else {
            await scrollToY((a.y == null ? 1 : a.y) * maxScroll(), a.dur || 1.2);
          }
          return true;
        }
        case 'type': {
          const el = elOf(a) || document.activeElement; if (!el) return false;
          el.focus();
          const setter = Object.getOwnPropertyDescriptor(el.__proto__, 'value')?.set;
          const text = a.text || '';
          for (let i = 1; i <= text.length; i++) {
            const v = text.slice(0, i);
            if (setter) setter.call(el, v); else el.value = v;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            await sleep(a.cps ? 1000 / a.cps : 60);
          }
          return true;
        }
        case 'press': {
          const el = elOf(a) || document.activeElement; if (!el) return false;
          for (const t of ['keydown', 'keyup'])
            el.dispatchEvent(new KeyboardEvent(t, { key: a.key, bubbles: true }));
          if (a.key === 'Enter' && el.form) el.form.requestSubmit?.();
          return true;
        }
        case 'select': {
          const el = elOf(a); if (!el) return false;
          if (a.label) {
            const opt = [...el.options].find(o => o.textContent.trim() === a.label);
            if (!opt) return false;
            el.value = opt.value;
          } else {
            el.value = a.value;
          }
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }
      }
      return false;
    },
    async point(a) {
      const el = elOf(a); if (!el) return null;
      const settle = a.settle == null ? 700 : a.settle;   // ms for scroll+reflow
      const glide = a.glide == null ? 0.5 : a.glide;      // s of cursor travel
      if (settle > 0) {
        el.scrollIntoView({ block: 'center', behavior: settle > 700 ? 'smooth' : 'auto' });
        await sleep(settle);
      }
      const r = el.getBoundingClientRect();
      if (glide > 0) await cursorToEl(el, glide);
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    },
    // Wait for a target the same way a click will find it. Waiting with
    // Playwright's own text= engine is not enough: on an app-router page it
    // also matches prefetched RSC payloads inside <script>, so it returns
    // instantly while the real button has not rendered yet. Sharing elOf()
    // means "wait until the next action can actually click it".
    async wait(a) {
      const deadline = Date.now() + (a.ms || 30000);
      while (Date.now() < deadline) {
        if (elOf(a)) return true;
        await sleep(150);
      }
      return false;
    },
  };
  return true;
}
"""


def local_src(src):
    """Resolve a page src to a local file (project first, template second)."""
    src = str(src).removeprefix("file://")
    if src.startswith(("http://", "https://")):
        return None
    p = Path(src)
    if p.is_absolute():
        return p
    for base in (lib.ROOT, lib.TEMPLATE):
        if (base / p).exists():
            return base / p
    return lib.ROOT / p


def scene_hash(scene, dur, cfg=None):
    """Fingerprint the scene + narration length. For page scenes backed by a
    local file, fingerprint the file too so HTML edits force a re-record.
    For card scenes, fingerprint the template file, theme, branding and
    vars so restyling a card forces a re-record."""
    extra = ""
    if scene.get("kind") == "page":
        p = local_src(scene.get("src", ""))
        if p and p.exists():
            extra = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    elif scene.get("kind") == "card" and cfg is not None:
        blob_theme = json.dumps({
            "template": scene.get("template", "title"),
            "theme": cfg.get("theme", {}),
            "branding": cfg.get("branding", {}),
            "vars": scene.get("vars", {}),
        }, sort_keys=True)
        extra = hashlib.sha256(blob_theme.encode()).hexdigest()[:16]
        tpl = lib.asset(f"cards/{scene.get('template', 'title')}.html")
        if tpl.exists():
            extra += hashlib.sha256(tpl.read_bytes()).hexdigest()[:16]
    blob = json.dumps({"scene": scene, "dur": round(dur, 2), "src": extra},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def term_html(title, lines):
    css = lib.asset("themes/terminal.css").read_text()
    spec = json.dumps({"title": title, "lines": lines})
    js = TERMINAL_JS.replace("__SPEC__", spec)
    return (f"<html><head><meta charset='utf-8'><style>{css}</style></head>"
            f"<body><div id='win'><div id='bar'>"
            f"<span class='dot' style='background:#ff5f57'></span>"
            f"<span class='dot' style='background:#febc2e'></span>"
            f"<span class='dot' style='background:#28c840'></span>"
            f"<span id='title'>{title}</span></div><div id='body'></div></div>"
            f"<script>{js}</script></body></html>")


def card_html(scene, cfg):
    template = scene.get("template", "title")
    path = lib.asset(f"cards/{template}.html")
    if not path.exists():
        sys.exit(f"unknown card template {template!r} ({path})")
    html = path.read_text()
    # Theme defaults first so old configs without a "theme" block still
    # resolve every {{accent1}} / {{bg}} / ... placeholder. Branding and
    # per-scene vars win over the theme.
    # NOTE: theme keys must NOT repeat branding keys (name, tagline, sub,
    # note, meta, headline, links, footnote) - branding text would clobber
    # the color. Themed colors use distinct names (subc, hi, hi2, ...).
    overlap = set(cfg.get("theme", {})) & set(cfg.get("branding", {}))
    if overlap:
        print(f"  ! theme keys collide with branding text: {sorted(overlap)}"
              " - rename the theme keys", file=sys.stderr)
    variables = {**lib.THEME_DEFAULTS, **cfg.get("theme", {}),
                 **cfg.get("branding", {}), **scene.get("vars", {})}
    # Convenience: {{kicker}} falls back to {{meta}} when a scene does not
    # set its own kicker line.
    if "kicker" not in variables and "meta" in variables:
        variables["kicker"] = variables["meta"]
    for k, v in variables.items():
        html = html.replace("{{" + k + "}}", str(v))
    if "{{" in html:
        left = sorted({p.split("}")[0] for p in html.split("{{")[1:]})
        print(f"  ! unresolved card placeholders: {left}", file=sys.stderr)
    # A single unclosed CSS brace silently swallows every rule after it: the
    # card renders as an empty frame and nothing else complains.
    if html.count("{") != html.count("}"):
        print(f"  ! card template {template!r} has unbalanced braces "
              f"({html.count('{')} open, {html.count('}')} close) — "
              "content after it will not render", file=sys.stderr)
    return html


def resolve_src(src):
    if src.startswith(("http://", "https://", "file://")):
        return src
    return local_src(src).resolve().as_uri()


def new_context(browser, cfg):
    # Authenticated demos need the session cookie in every scene, because each
    # scene is a fresh browser context. Point DEMO_STORAGE_STATE at a Playwright
    # storage-state JSON to start signed in without replaying the login screen.
    storage_state = os.environ.get("DEMO_STORAGE_STATE")
    ctx = browser.new_context(
        viewport={"width": cfg["width"], "height": cfg["height"]},
        record_video_dir=str(lib.CLIPS),
        record_video_size={"width": cfg["width"], "height": cfg["height"]},
        **({"storage_state": storage_state} if storage_state else {}),
    )
    # Optional page prelude. A demo of a product that needs a wallet cannot be
    # recorded with a wallet popup in the way, so a project may point
    # DEMO_INIT_SCRIPT at a script that installs one. Nothing is injected unless
    # the environment asks for it, which keeps every other recording honest.
    init_script = os.environ.get("DEMO_INIT_SCRIPT")
    if init_script:
        ctx.add_init_script(path=init_script)
    return ctx


def wallet_mode(scene, cfg):
    """Which wallet surface a page scene wants.

    "inject" is the demo mode: accounts come from wallets/.env and are already
    connected, so no popup is filmed. A bare `"crypto": true` uses it when a
    key is configured and falls back to the MetaMask profile when not.
    """
    mode = scene.get("wallet") or cfg.get("wallet")
    if isinstance(mode, str) and mode.strip().lower() in wallet_inject.MODES:
        return "inject"
    if not mode and scene.get("crypto"):
        return "inject" if wallet_inject.keys_available() else wallet_lib.DEFAULT_WALLET
    if not mode:
        return None
    return wallet_lib.resolve_wallet(mode)


def new_inject_context(browser, scene, cfg):
    """Plain context + a provider that is already connected."""
    ctx = new_context(browser, cfg)
    wallet = wallet_inject.Wallet.from_env(
        chain=scene.get("chain") or cfg.get("chain") or "evm",
        chain_id=scene.get("chain_id") or cfg.get("chain_id"),
    )
    ctx.expose_binding("__demo_wallet_call",
                       lambda _source, payload: wallet.handle(payload))
    ctx.add_init_script(script=wallet_inject.init_script(wallet))
    if wallet.evm:
        who, chain = wallet.evm_address, wallet.resolve_chain_id()
    else:
        who, chain = wallet.sol_address, wallet.sol_cluster()
    print(f"  wallet  injected {who[:6]}...{who[-4:]}  chain {chain}")
    return ctx, wallet


def new_wallet_context(playwright, wallet, cfg, headless=False):
    """Persistent profile with a real wallet extension loaded.

    Import the seed once with scripts/wallet_lib.py setup <wallet>; this
    reuses wallets/profiles/<wallet>/ for every clip.
    """
    if playwright is None:
        raise RuntimeError("wallet scenes need the Playwright instance")
    return wallet_lib.launch_context(
        playwright,
        wallet,
        headless=headless,
        viewport={"width": cfg["width"], "height": cfg["height"]},
        record_video_dir=str(lib.CLIPS),
        record_video_size={"width": cfg["width"], "height": cfg["height"]},
    )


def save_clip(pg, ctx, sid, action_time=None):
    video = pg.video
    ctx.close()
    dest = lib.CLIPS / f"{sid}.webm"
    try:
        video.save_as(str(dest))
    except Exception:
        # A persistent (wallet) context closes the whole browser, which can
        # invalidate the video artifact. The temp .webm is already on disk.
        temp = video.path()
        if not temp or not Path(temp).exists():
            raise
        shutil.copy2(temp, dest)
        if Path(temp) != dest:
            Path(temp).unlink(missing_ok=True)
    temp = video.path()
    if temp and Path(temp).exists() and Path(temp) != dest:
        Path(temp).unlink(missing_ok=True)
    if action_time is not None:
        # Record how long the scene's own beats actually took so the build step
        # can never trim a scene shorter than its own content.
        (lib.CLIPS / f"{sid}.json").write_text(
            json.dumps({"action_time": round(action_time, 2)}) + "\n")
    return dest


def record_static(browser, sid, scene, dur, cfg):
    ctx = new_context(browser, cfg)
    pg = ctx.new_page()
    if scene["kind"] == "term":
        pg.set_content(term_html(scene.get("title", sid), scene["lines"]),
                       wait_until="load")
    else:
        pg.set_content(card_html(scene, cfg), wait_until="load")
    trim = float(scene.get("trim", cfg["trim"]))
    pg.wait_for_timeout(int((trim + dur + 1.8) * 1000))
    save_clip(pg, ctx, sid)
    return trim


def record_page(browser, sid, scene, dur, cfg, playwright=None):
    wallet = wallet_mode(scene, cfg)
    injected = None
    if wallet == "inject":
        ctx, injected = new_inject_context(browser, scene, cfg)
        pg = ctx.new_page()
    elif wallet:
        ctx = new_wallet_context(
            playwright, wallet, cfg,
            headless=bool(scene.get("headless", False)),
        )
        if scene.get("unlock", True):
            wallet_lib.unlock(
                ctx, wallet,
                password=scene.get("wallet_password"),
                timeout=float(scene.get("unlock_timeout", 20)),
            )
        pg = ctx.new_page()
        pg.bring_to_front()
    else:
        ctx = new_context(browser, cfg)
        pg = ctx.new_page()
    zoom = float(scene.get("zoom", 1.0))

    def ensure_demo(quiet=False):
        """Re-inject the scripted-cursor helpers.

        A product that navigates between steps (SPA link, full page load)
        replaces the document, so window.__DEMO and the cursor overlay are gone
        on the next action. Re-inject instead of failing the scene.
        """
        try:
            if not pg.evaluate("() => !!window.__DEMO"):
                pg.evaluate(PAGE_JS)
                pg.evaluate("z => window.__DEMO.setup(z)", zoom)
        except Exception as e:
            if not quiet:
                print(f"  ! {sid}: re-inject failed: {str(e)[:80]}",
                      file=sys.stderr)

    def wait_target(sel, timeout_ms):
        """Block until `sel` is clickable, tolerating navigation.

        A wait is normally interrupted by the very navigation it waits for, so
        each attempt is short and a destroyed execution context just means
        "the page moved on - look again in the new document".
        """
        deadline = time.time() + timeout_ms / 1000.0
        while True:
            remaining = int((deadline - time.time()) * 1000)
            if remaining <= 0:
                return False
            ensure_demo(quiet=True)
            try:
                if pg.evaluate("a => window.__DEMO.wait(a)",
                               {"sel": sel, "ms": min(remaining, 1500)}):
                    return True
            except Exception:
                pass  # navigated mid-wait: look again in the new document

    t0 = time.time()
    pg.goto(resolve_src(scene["src"]), wait_until="domcontentloaded", timeout=90000)
    ensure_demo()
    for sel in scene.get("wait_for", []):
        if not wait_target(sel, 45000):
            print(f"  ! {sid}: selector {sel!r} not found", file=sys.stderr)
    pg.wait_for_timeout(int(float(scene.get("settle", 1.0)) * 1000))
    ensure_demo()
    # Pacing: how long the recorder pauses before firing a click. A fast
    # product demo (many approvals in a row) reads better with a tight hold,
    # so scenes may override the default per scene.
    hold = int(float(scene.get("hold", 0.9)) * 1000)
    t_actions = time.time()
    for a in scene.get("actions", []):
        ensure_demo()
        act = a.get("action")
        if os.environ.get("DEMO_DEBUG"):
            print(f"  t {time.time()-t_actions:6.2f}s {sid} {act} {a.get('sel')!r}"
                  f" url={pg.url.split('3100')[-1] or '/'}", file=sys.stderr)
        if injected is not None and act in ("wallet_unlock", "wallet_approve",
                                            "wallet_click"):
            # The account is already connected: a script written for the
            # extension flow still runs, its wallet steps just do nothing.
            if os.environ.get("DEMO_DEBUG"):
                print(f"  t {time.time()-t_actions:6.2f}s {sid} "
                      f"{act} skipped (injected wallet)", file=sys.stderr)
            if a.get("after"):
                pg.wait_for_timeout(int(a["after"] * 1000))
            continue
        if act == "wallet_unlock":
            ok = wallet_lib.unlock(
                ctx, scene.get("wallet"),
                password=a.get("password"),
                timeout=float(a.get("timeout", 20)),
            )
            if not ok:
                print(f"  ! {sid}: wallet unlock failed", file=sys.stderr)
            if a.get("after"):
                pg.wait_for_timeout(int(a["after"] * 1000))
            continue
        if act == "wallet_approve":
            ok = wallet_lib.approve(
                scene.get("wallet") or cfg.get("wallet") or wallet_lib.DEFAULT_WALLET,
                ctx,
                kind=a.get("kind", "connect"),
                chain=a.get("chain", scene.get("chain", cfg.get("chain", "evm"))),
                timeout=float(a.get("timeout", 25)),
            )
            if not ok:
                print(f"  ! {sid}: wallet popup to approve was not found",
                      file=sys.stderr)
            if a.get("after"):
                pg.wait_for_timeout(int(a["after"] * 1000))
            continue
        if act == "wallet_click":
            popup = wallet_lib.wait_for_popup(
                ctx, timeout=float(a.get("timeout", 20)))
            hit = None
            if popup is not None:
                hit = wallet_lib.click_first(
                    popup, [a.get("text", "")],
                    timeout=float(a.get("click_timeout", 8)),
                )
            if not hit:
                print(f"  ! {sid}: wallet popup text {a.get('text')!r} not found",
                      file=sys.stderr)
            if a.get("after"):
                pg.wait_for_timeout(int(a["after"] * 1000))
            continue
        if act in ("click", "hover"):
            pt = pg.evaluate("a => window.__DEMO.point(a)", a)
            pg.wait_for_timeout(int(a.get("hold", hold)))
            if pt:
                pg.mouse.move(pt["x"], pt["y"])
                if act == "click":
                    pg.mouse.click(pt["x"], pt["y"])
            else:
                if os.environ.get("DEMO_DEBUG"):
                    dbg = pg.evaluate(
                        "sel => ({url: location.pathname, demo: typeof window.__DEMO,"
                        " anchors: [...document.querySelectorAll('a')].map(a => a.textContent.trim().slice(0,40))})",
                        a.get("sel"))
                    print(f"  ? {sid}: miss on {a.get('sel')!r} -> {dbg}",
                          file=sys.stderr)
                print(f"  ! {sid}: {act} target {a.get('sel')!r} not found",
                      file=sys.stderr)
        else:
            ok = pg.evaluate("a => window.__DEMO.run(a)", a)
            if ok is False:
                print(f"  ! {sid}: action {act} target {a.get('sel')!r} not found",
                      file=sys.stderr)
        if a.get("after"):
            pg.wait_for_timeout(int(a["after"] * 1000))
        # Product demos are slow and variable: after an action, wait for the
        # element the next beat depends on instead of guessing a delay. Uses
        # __DEMO.wait (same matcher as the click) - see PAGE_JS.
        for sel in a.get("wait_for", []) or []:
            got = wait_target(sel, int(a.get("wait_timeout", 30000)))
            if not got:
                print(f"  ! {sid}: post-action target {sel!r} never rendered",
                      file=sys.stderr)
                if os.environ.get("DEMO_DEBUG"):
                    dump = pg.evaluate(
                        "() => ({url: location.pathname, buttons:"
                        " [...document.querySelectorAll('button')].map(b => b.textContent.trim().slice(0,40)),"
                        " alerts: [...document.querySelectorAll('[role=alert], .alert, strong')]"
                        "   .map(a => a.textContent.trim().slice(0,90)).slice(0,6)})")
                    print(f"  ? {sid}   page={dump}", file=sys.stderr)
            if os.environ.get("DEMO_DEBUG"):
                print(f"  t {time.time()-t_actions:6.2f}s {sid}   wait {sel!r}"
                      f" -> {got} url={pg.url.split('3100')[-1] or '/'}",
                      file=sys.stderr)
    # `trim` is the settled time before the first beat (page paint, fonts,
    # cursor fade-in); `action_time` is how long the whole scene really needs,
    # which is what the build uses to keep a slow app from being cut short.
    preroll = t_actions - t0
    trim = max(0.0, round(preroll - 0.6, 2))
    action_time = time.time() - t0
    while time.time() - t0 < max(trim + dur, action_time) + 1.2:
        pg.wait_for_timeout(300)
    save_clip(pg, ctx, sid)
    return trim, action_time


def main():
    ap = argparse.ArgumentParser()
    lib.project_arg(ap)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    lib.init(args.project)
    lib.ensure_dirs()
    print(f"project: {lib.project_label()}")
    cfg = lib.load_config()
    segments = lib.load_segments()
    chrome = lib.chromium_bin()
    if chrome:
        print(f"chromium: {chrome}")
    else:
        print("chromium: playwright bundle")

    todo = []
    for seg in segments:
        sid = seg["id"]
        scene = seg.get("scene")
        if not scene:
            sys.exit(f"segment {sid} has no scene in script/story.json")
        if args.only and sid not in args.only:
            continue
        side = lib.CLIPS / f"{sid}.json"
        clip = lib.CLIPS / f"{sid}.webm"
        h = scene_hash(scene, seg["dur"], cfg)
        if scene.get("kind") == "page" and wallet_mode(scene, cfg) == "inject":
            # The address is on camera, so a different demo account means a
            # different clip.
            h = hashlib.sha256(
                (h + wallet_inject.fingerprint_env()).encode()).hexdigest()[:16]
        if not args.force and clip.exists() and side.exists() \
                and lib.load_json(side).get("hash") == h:
            print(f"  {sid:<16} cached")
            continue
        todo.append((sid, scene, seg["dur"], h))

    if not todo:
        print("record: nothing to do")
        return

    with sync_playwright() as p:
        kw = {"args": ["--no-sandbox"]}
        if chrome:
            kw["executable_path"] = chrome
        browser = p.chromium.launch(**kw)
        for sid, scene, dur, h in todo:
            kind = scene.get("kind")
            t0 = time.time()
            elapsed = None
            if kind in ("term", "card"):
                trim = record_static(browser, sid, scene, dur, cfg)
            elif kind == "page":
                trim, elapsed = record_page(browser, sid, scene, dur, cfg, playwright=p)
            else:
                sys.exit(f"{sid}: unknown scene kind {kind!r} "
                         "(expected card, term, or page)")
            sidecar = {"trim": trim, "hash": h}
            if elapsed is not None:
                # How long the scene's own beats took. The build step extends a
                # segment when its content outlasts the narration, so the last
                # click of a slow app is never trimmed off.
                sidecar["action_time"] = round(elapsed, 2)
            lib.save_json(lib.CLIPS / f"{sid}.json", sidecar)
            print(f"  {sid:<16} {kind:<5} {dur:6.2f}s  "
                  f"recorded in {time.time() - t0:.1f}s (trim {trim}s)")
        browser.close()


if __name__ == "__main__":
    main()
