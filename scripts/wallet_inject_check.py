#!/usr/bin/env python3
"""Exercise the injected wallet in a real browser.

Loads wallets/inject-dapp/index.html with the same provider the recorder
installs, then asks the page to connect and sign on both chains. Prints the
addresses and whether each call worked; no key material is printed.

    python scripts/wallet_inject_check.py
    python scripts/wallet_inject_check.py --headed
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
import wallet_inject  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    lib.init(None)

    wallet = wallet_inject.Wallet.from_env(chain="evm")
    if not wallet.sol:
        print("note: no SOL_PRIVATE_KEY, the Solana half will be skipped")

    page_path = lib.TEMPLATE / "wallets" / "inject-dapp" / "index.html"
    chrome = lib.chromium_bin()
    with sync_playwright() as p:
        kw = {"headless": not args.headed, "args": ["--no-sandbox"]}
        if chrome:
            kw["executable_path"] = chrome
        browser = p.chromium.launch(**kw)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        ctx.expose_binding("__demo_wallet_call",
                           lambda _source, payload: wallet.handle(payload))
        ctx.add_init_script(script=wallet_inject.init_script(wallet))
        page = ctx.new_page()
        page.goto(page_path.resolve().as_uri(), wait_until="load")
        result = page.evaluate("() => window.runCheck()")
        browser.close()

    ok = True
    evm = result.get("evm")
    if evm:
        print(f"evm  {evm['address']}  signature {evm['signature'][:18]}...")
    else:
        ok = False
        print("evm  FAILED")
    sol = result.get("sol")
    if sol:
        print(f"sol  {sol['address']}  signature {sol['signature'][:16]}...")
    elif wallet.sol:
        ok = False
        print("sol  FAILED")
    for err in result.get("errors", []):
        ok = False
        print(f"     {err}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
