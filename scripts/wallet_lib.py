"""Local MetaMask profile for crypto demo video scenes.

MetaMask is the supported wallet: its accounts cover EVM and Solana from one
seed. The extension runs in a persistent Chromium profile; import the seed
once and the wallet survives every recording run. Phantom support is kept as
an optional legacy path.

Nothing here ever reads or stores the seed phrase: the user types it into the
wallet UI. Profiles live in wallets/profiles/<wallet>/ and are gitignored.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WALLET_ROOT = ROOT / "wallets"
EXT_ROOT = WALLET_ROOT / "extensions"
PROFILE_ROOT = WALLET_ROOT / "profiles"
TEST_DAPP_ROOT = WALLET_ROOT / "test-dapp"
TEST_DAPP_PORT = 8765

# Local unlock passwords for the test wallets. They only unlock the browser
# profile; they are never used as seeds and cannot move funds on their own.
# Override one with METAMASK_PASSWORD / PHANTOM_PASSWORD, or both with
# WALLET_PASSWORD.
DEFAULT_PASSWORDS = {
    "metamask": "123123123",
    "phantom": "@hN0pass12",
}


def password_for(wallet: str) -> str:
    wallet = resolve_wallet(wallet)
    spec = wallet_dir(wallet)
    env_key = f"{wallet.upper()}_PASSWORD"
    return (
        os.environ.get(env_key)
        or os.environ.get("WALLET_PASSWORD")
        or DEFAULT_PASSWORDS[wallet]
    )

# Chrome Web Store ids and CRX download URLs. The unpacked extension is
# downloaded once and reused; no Chrome Web Store account is needed.
WALLETS = {
    "metamask": {
        "label": "MetaMask",
        "crx_id": "nkbihfbeogaeaoehlefnkodbefgpgknn",
        "onboarding": "home.html",
        "lock_url": "home.html#/unlock",
        "import_hint": (
            "Click 'I have an existing wallet', then 'Import using Secret "
            "Recovery Phrase', paste your TEST seed phrase, set a local "
            "password, and finish."
        ),
        "ready_text": ("Account", "Ethereum"),
        "not_ready_text": ("Create a new wallet", "I have an existing wallet"),
    },
    "phantom": {
        "label": "Phantom",
        "crx_id": "bfnaelmomeimhlpmgjnjophhpkkoljpa",
        "onboarding": "onboarding.html",
        "lock_url": "onboarding.html",
        "import_hint": (
            "Click 'I Already Have a Wallet', then 'Import Recovery Phrase', "
            "paste your TEST seed phrase, set a local password, and finish."
        ),
        "ready_text": ("Account", "Solana"),
        "not_ready_text": ("Import a wallet", "Create a new wallet"),
    },
}

# MetaMask is the supported wallet for crypto demos (EVM + Solana accounts).
# Phantom is kept as an optional legacy profile, but is not required.
DEFAULT_WALLET = "metamask"
REQUIRED_WALLETS = ("metamask",)


def resolve_wallet(wallet: str | None = None) -> str:
    """Return a valid wallet name, defaulting to MetaMask."""
    if not wallet or wallet is True:
        return DEFAULT_WALLET
    if wallet not in WALLETS:
        raise SystemExit(f"unknown wallet {wallet!r} (choose metamask)")
    return wallet


def wallet_dir(wallet: str) -> Path:
    if wallet not in WALLETS:
        raise SystemExit(f"unknown wallet {wallet!r} (choose metamask or phantom)")
    return WALLETS[wallet]


def extension_path(wallet: str) -> Path:
    return EXT_ROOT / wallet


def profile_path(wallet: str) -> Path:
    return PROFILE_ROOT / wallet


def crx_download_url(crx_id: str) -> str:
    return (
        "https://clients2.google.com/service/update2/crx"
        "?response=redirect&prodversion=149.0.0.0&acceptformat=crx2,crx3"
        f"&x=id%3D{crx_id}%26uc"
    )


def _extract_crx(crx: bytes, dest: Path) -> None:
    """Extract a CRX2/CRX3 file (a ZIP with a header) without external tools."""
    if crx[:4] != b"Cr24":
        raise RuntimeError("not a CRX file")
    version = struct.unpack("<I", crx[4:8])[0]
    if version == 3:
        header_len = struct.unpack("<I", crx[8:12])[0]
        zip_start = 12 + header_len
    elif version == 2:
        pubkey_len = struct.unpack("<I", crx[8:12])[0]
        sig_len = struct.unpack("<I", crx[12:16])[0]
        zip_start = 16 + pubkey_len + sig_len
    else:
        raise RuntimeError(f"unsupported CRX version {version}")
    if crx[zip_start:zip_start + 4] != b"PK\x03\x04":
        raise RuntimeError("CRX payload is not a ZIP archive")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(crx[zip_start:])) as z:
        z.extractall(dest)


def ensure_extension(wallet: str, quiet: bool = False) -> Path:
    """Download + unpack the extension if it is not already present."""
    spec = wallet_dir(wallet)
    dest = extension_path(wallet)
    if (dest / "manifest.json").exists():
        return dest
    if not quiet:
        print(f"  downloading {spec['label']} extension ...", file=sys.stderr)
    url = crx_download_url(spec["crx_id"])
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                crx = r.read()
            break
        except Exception as e:
            if attempt == 3:
                raise SystemExit(
                    f"could not download {spec['label']} extension: {e}\n"
                    f"download it manually and unpack it into {dest}"
                )
            time.sleep(2)
    if dest.exists():
        shutil.rmtree(dest)
    _extract_crx(crx, dest)
    if not (dest / "manifest.json").exists():
        raise SystemExit(f"{spec['label']} extension did not unpack correctly")
    if not quiet:
        print(f"  {spec['label']} extension -> {dest}", file=sys.stderr)
    return dest


def launch_context(
    playwright,
    wallet: str,
    *,
    headless: bool = False,
    viewport: dict | None = None,
    record_video_dir: str | None = None,
    record_video_size: dict | None = None,
):
    """Launch a persistent Chromium context with one wallet extension loaded."""
    wallet = resolve_wallet(wallet)
    spec = wallet_dir(wallet)
    ext = ensure_extension(wallet, quiet=True)
    profile = profile_path(wallet)
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        f"--disable-extensions-except={ext}",
        f"--load-extension={ext}",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    kwargs = {
        "headless": headless,
        "channel": "chromium",
        "args": args,
        "viewport": viewport or {"width": 1440, "height": 900},
    }
    if record_video_dir:
        kwargs["record_video_dir"] = str(record_video_dir)
    if record_video_size:
        kwargs["record_video_size"] = record_video_size
    ctx = playwright.chromium.launch_persistent_context(str(profile), **kwargs)
    ctx._wallet_name = wallet  # type: ignore[attr-defined]
    ctx._wallet_label = spec["label"]  # type: ignore[attr-defined]
    return ctx


def extension_id(ctx, timeout: float = 15.0) -> str:
    """Find the extension id from the MV3 service worker (or a page URL)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sw in ctx.service_workers:
            url = sw.url
            if url.startswith("chrome-extension://"):
                return url.split("/")[2]
        for pg in ctx.pages:
            if pg.url.startswith("chrome-extension://"):
                return pg.url.split("/")[2]
        time.sleep(0.25)
    raise RuntimeError("could not find the wallet extension service worker")


def wallet_page_url(wallet: str, ext_id: str) -> str:
    return f"chrome-extension://{ext_id}/{wallet_dir(wallet)['onboarding']}"


def open_wallet(ctx, wallet: str):
    ext_id = extension_id(ctx)
    page = ctx.new_page()
    page.goto(wallet_page_url(wallet, ext_id), wait_until="domcontentloaded", timeout=30000)
    return page


def body_text(page) -> str:
    try:
        return page.inner_text("body")
    except Exception:
        return ""


def is_initialized(ctx, wallet: str) -> bool:
    """Heuristic: a wallet page is showing an account, and none is onboarding."""
    spec = wallet_dir(wallet)
    ready = False
    for page in ctx.pages:
        if not page.url.startswith("chrome-extension://"):
            continue
        text = body_text(page)
        if not text:
            continue
        low = text.lower()
        if any(t.lower() in low for t in spec["not_ready_text"]):
            return False
        if "import using secret recovery phrase" in low:
            return False
        if "to get started, create a new wallet" in low:
            return False
        if "import an existing wallet" in low:
            return False
        home_markers = ("send", "receive", "swap", "buy")
        if "account" in low and any(m in low for m in home_markers):
            ready = True
    return ready

def wait_until_initialized(ctx, wallet: str, timeout: float = 900.0,
                          poll: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_initialized(ctx, wallet):
            return True
        time.sleep(poll)
    return False


def _wallet_pages(ctx, ext_id: str):
    prefix = f"chrome-extension://{ext_id}/"
    return [p for p in ctx.pages if p.url.startswith(prefix)]


def unlock(ctx, wallet: str, password: str | None = None,
           timeout: float = 40.0, close: bool = False) -> bool:
    """Unlock the wallet profile with its local password.

    Uses the tab Chromium already opened instead of creating a second wallet
    page, then keeps exactly one unlocked wallet tab open.
    """
    spec = wallet_dir(wallet)
    password = password or password_for(wallet)
    ext_id = extension_id(ctx)
    deadline = time.time() + timeout

    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(f"chrome-extension://{ext_id}/{spec.get('lock_url', spec['onboarding'])}",
                  wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass

    unlocked = False
    while time.time() < deadline:
        try:
            text = body_text(page)
        except Exception:
            text = ""
        low = text.lower()
        # MetaMask has stable test ids for the lock form.
        mm_pw = page.locator('[data-testid="unlock-password"]')
        pw = page.locator("input[type=password]")
        if mm_pw.count() > 0:
            try:
                mm_pw.first.fill(password)
                page.locator('[data-testid="unlock-submit"]').first.click()
                page.wait_for_timeout(1500)
            except Exception:
                pass
        elif pw.count() > 0:
            try:
                pw.first.fill(password)
                clicked = click_first(page, ["Unlock", "Continue", "Confirm"], timeout=5.0)
                if clicked:
                    page.wait_for_timeout(1500)
            except Exception:
                pass
        elif "account" in low:
            unlocked = True
            break
        page.wait_for_timeout(700)

    if not unlocked:
        for _ in range(12):
            low = body_text(page).lower()
            if "account" in low and page.locator("input[type=password]").count() == 0:
                unlocked = True
                break
            page.wait_for_timeout(500)
    if not unlocked:
        return False

    # Keep exactly one wallet tab: the unlocked one.
    for p in list(ctx.pages):
        if p is page:
            continue
        if p.url.startswith(f"chrome-extension://{ext_id}/"):
            try:
                p.close()
            except Exception:
                pass
    if close:
        try:
            page.close()
        except Exception:
            pass
    return True

def setup_profile(wallet: str, *, headless: bool = False,
                  timeout: float = 900.0) -> int:
    """Open a profile's onboarding page and wait for the user to import.

    The browser stays open for `timeout` seconds. When the wallet looks
    initialized, the context is closed and the profile is kept on disk.
    """
    from playwright.sync_api import sync_playwright

    spec = wallet_dir(wallet)
    print(f"{spec['label']} profile: {profile_path(wallet)}")
    print(f"extension:      {extension_path(wallet)}")
    print()
    print("A browser window should open. Import the wallet manually:")
    print(f"  {spec['import_hint']}")
    print()
    print(f"Use this local wallet password: {password_for(wallet)}")
    print("Use a TEST-ONLY seed phrase. Never use a seed that holds real funds.")
    print("The profile is saved automatically; it is not stored in git.")
    print()
    with sync_playwright() as p:
        ctx = launch_context(p, wallet, headless=headless)
        page = open_wallet(ctx, wallet)
        print(f"opened: {page.url}")
        print("waiting for the wallet to finish importing ...")
        ok = wait_until_initialized(ctx, wallet, timeout=timeout)
        if ok:
            print(f"{spec['label']} looks initialized. profile saved.")
        else:
            print(f"timed out waiting for {spec['label']} onboarding to finish.")
            print("The profile is still saved; re-run this command to continue.")
        ctx.close()
    return 0 if ok else 1


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve_test_dapp(port: int = TEST_DAPP_PORT) -> ThreadingHTTPServer:
    """Serve wallets/test-dapp on 127.0.0.1:<port>."""
    handler = lambda *a, **kw: _QuietHandler(  # noqa: E731
        *a, directory=str(TEST_DAPP_ROOT), **kw)
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError:
        # Another verify run (or a manual `python -m http.server`) owns it.
        class _AlreadyRunning:
            def shutdown(self):
                return None
        return _AlreadyRunning()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def test_dapp_url(port: int = TEST_DAPP_PORT) -> str:
    return f"http://127.0.0.1:{port}/"


def _visible(page, sel: str) -> bool:
    try:
        loc = page.locator(sel).first
        return loc.is_visible()
    except Exception:
        return False


def click_first(page, texts, *, timeout: float = 4.0) -> str | None:
    """Click the first visible button/link whose text matches one of `texts`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for text in texts:
            for sel in (f"button:has-text({json.dumps(text)})",
                        f"[role=button]:has-text({json.dumps(text)})",
                        f"text={text}"):
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible() and loc.is_enabled():
                        loc.click(timeout=2500)
                        return text
                except Exception:
                    continue
        time.sleep(0.25)
    return None


def wallet_popups(ctx):
    """Pages that look like a wallet approval popup, not the wallet home."""
    out = []
    for page in ctx.pages:
        url = page.url
        if not url.startswith("chrome-extension://"):
            continue
        if any(x in url for x in ("notification.html", "confirm", "sign",
                                  "send", "connect", "approval")):
            out.append(page)
    return out


def wait_for_popup(ctx, timeout: float = 20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pages = wallet_popups(ctx)
        if pages:
            return pages[-1]
        time.sleep(0.25)
    return None


def approve(wallet: str, ctx, *, kind: str = "connect",
            chain: str = "evm", timeout: float = 30.0) -> bool:
    """Approve a pending wallet request.

    Rather than depending on a popup window, this opens the extension's
    notification page, which shows the latest pending request. Opening it
    once (not reloading) is important: reloading can drop the request.
    """
    wallet = resolve_wallet(wallet)
    ext_id = extension_id(ctx)
    # MetaMask uses the same notification surface for EVM and Solana requests;
    # only the wording differs, so keep the target list tolerant.
    target = {
        "connect": ("connect this website", "connect", "approve"),
        "sign": ("signature request", "sign", "confirm"),
        "transaction": ("confirm", "approve", "sign"),
    }.get(kind, ("confirm", "approve"))

    page = None
    for p in ctx.pages:
        if "notification.html" in p.url:
            page = p
            break
    created = False
    if page is None:
        time.sleep(1.2)
        page = ctx.new_page()
        created = True
        try:
            page.goto(f"chrome-extension://{ext_id}/notification.html",
                      wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass

    # Wait for the request UI to render. Do not reload the page.
    deadline = time.time() + timeout
    body = ""
    while time.time() < deadline:
        body = body_text(page)
        low = body.lower()
        if target[0] in low:
            break
        if kind == "connect" and "connect" in low and "account" in low:
            break
        if kind == "sign" and "signature" in low:
            break
        page.wait_for_timeout(500)

    if not body:
        if created:
            try:
                page.close()
            except Exception:
                pass
        return False

    selectors = []
    if wallet == "metamask":
        if kind == "connect":
            selectors = [
                'button:has-text("Connect")',
                '[data-testid="page-container-footer-next"]',
                'button:has-text("Next")',
                'button:has-text("Approve")',
            ]
        elif kind == "sign":
            selectors = [
                '[data-testid="request-signature__sign"]',
                '[data-testid="signature-sign-button"]',
                'button:has-text("Sign")',
                'button:has-text("Confirm")',
            ]
        else:
            selectors = [
                '[data-testid="page-container-footer-next"]',
                'button:has-text("Confirm")',
                'button:has-text("Approve")',
            ]
    else:
        if kind == "connect":
            selectors = [
                'button:has-text("Connect")',
                'button:has-text("Approve")',
                'button:has-text("Confirm")',
            ]
        elif kind == "sign":
            selectors = [
                'button:has-text("Sign")',
                'button:has-text("Approve")',
                'button:has-text("Confirm")',
            ]
        else:
            selectors = [
                'button:has-text("Approve")',
                'button:has-text("Confirm")',
                'button:has-text("Sign")',
            ]

    clicked = False
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible() and loc.is_enabled():
                loc.click(timeout=5000)
                clicked = True
                break
        except Exception:
            continue
    if clicked:
        page.wait_for_timeout(1200)
    if created:
        try:
            page.close()
        except Exception:
            pass
    return clicked

def profile_status(wallet: str) -> dict:
    spec = wallet_dir(wallet)
    ext = extension_path(wallet)
    prof = profile_path(wallet)
    return {
        "wallet": spec["label"],
        "extension": str(ext),
        "extension_installed": (ext / "manifest.json").exists(),
        "profile": str(prof),
        "profile_exists": prof.exists(),
        "profile_bytes": sum(p.stat().st_size for p in prof.rglob("*") if p.is_file())
        if prof.exists() else 0,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="MetaMask / Phantom Playwright profiles")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install", help="download and unpack extensions")
    p_install.add_argument("wallet", nargs="?", choices=sorted(WALLETS))

    p_setup = sub.add_parser("setup", help="open onboarding for manual import")
    p_setup.add_argument("wallet", choices=sorted(WALLETS))
    p_setup.add_argument("--headless", action="store_true")
    p_setup.add_argument("--timeout", type=float, default=900.0)

    p_unlock = sub.add_parser("unlock", help="unlock a profile with its local password")
    p_unlock.add_argument("wallet", choices=sorted(WALLETS))

    p_status = sub.add_parser("status", help="show extension/profile state")
    p_status.add_argument("wallet", nargs="?", choices=sorted(WALLETS))

    args = ap.parse_args(argv)
    if args.cmd == "install":
        wallets = [args.wallet] if args.wallet else list(REQUIRED_WALLETS)
        for w in wallets:
            ensure_extension(w)
        return 0
    if args.cmd == "setup":
        return setup_profile(args.wallet, headless=args.headless,
                             timeout=args.timeout)
    if args.cmd == "unlock":
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = launch_context(p, args.wallet, headless=False)
            ok = unlock(ctx, args.wallet)
            print(f"{wallet_dir(args.wallet)['label']} unlocked: {ok}")
            ctx.close()
        return 0 if ok else 1
    if args.cmd == "status":
        wallets = [args.wallet] if args.wallet else list(REQUIRED_WALLETS)
        for w in wallets:
            print(json.dumps(profile_status(w), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
