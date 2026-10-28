"""Smoke-test a MetaMask/Phantom Playwright profile.

Opens wallets/test-dapp, connects, signs a harmless message, and prints the
address/signature. It never broadcasts a transaction.

Use --manual to approve the wallet popups yourself (useful the first time,
while you are checking the profile). Use --keep-open to leave the browser
open after the test.
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

import wallet_lib as W


def wait_for_js(page, expr: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if page.evaluate(expr):
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="verify a local wallet profile")
    ap.add_argument("wallet", nargs="?", default=W.DEFAULT_WALLET,
                    choices=sorted(W.WALLETS))
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--manual", action="store_true",
                    help="do not auto-click the wallet popup")
    ap.add_argument("--keep-open", action="store_true")
    args = ap.parse_args()

    # A fresh port means a fresh origin, so the wallet must show a connect
    # request instead of silently reusing an earlier connection.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    httpd = W.serve_test_dapp(port)
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = W.launch_context(p, args.wallet, headless=args.headless)
            print("unlocking wallet ...")
            print("  unlocked:", W.unlock(ctx, args.wallet))
            page = ctx.new_page()
            page.goto(W.test_dapp_url(port), wait_until="domcontentloaded", timeout=30000)
            time.sleep(1.0)
            print(f"opened {W.test_dapp_url(port)} with {args.wallet}")

            if args.wallet == "metamask":
                page.click("#evm-connect")
                if not args.manual:
                    print("approving connect ...")
                    print("  clicked:", W.approve("metamask", ctx, kind="connect"))
                ok = wait_for_js(page, "() => !!window.__EVM_CONNECTED__", 30)
                print("connected:", ok)
                if ok:
                    print(page.inner_text("#evm-out"))
                    page.click("#evm-sign")
                    if not args.manual:
                        print("approving signature ...")
                        print("  clicked:", W.approve("metamask", ctx, kind="sign"))
                    signed = wait_for_js(page, "() => !!window.__EVM_SIGNED__", 30)
                    print("signed:", signed)
                    if signed:
                        print(page.inner_text("#evm-out"))
            else:
                page.click("#sol-connect")
                if not args.manual:
                    print("approving connect ...")
                    print("  clicked:", W.approve("phantom", ctx, kind="connect"))
                ok = wait_for_js(page, "() => !!window.__SOL_CONNECTED__", 30)
                print("connected:", ok)
                if ok:
                    print(page.inner_text("#sol-out"))
                    page.click("#sol-sign")
                    if not args.manual:
                        print("approving signature ...")
                        print("  clicked:", W.approve("phantom", ctx, kind="sign"))
                    signed = wait_for_js(page, "() => !!window.__SOL_SIGNED__", 30)
                    print("signed:", signed)
                    if signed:
                        print(page.inner_text("#sol-out"))

            if args.keep_open:
                input("Press Enter to close the browser ...")
            ctx.close()
    finally:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
