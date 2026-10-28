# Local MetaMask profile for video recording

A real MetaMask extension in a **persistent Playwright profile**. Import a
test seed once and the wallet survives every recording run.

MetaMask is the supported wallet for crypto demos. It holds EVM accounts and
Solana accounts from the same seed, so one profile covers both.

```
wallets/
├── extensions/metamask/   unpacked extension (gitignored)
├── profiles/metamask/     persistent Chromium profile (gitignored)
├── test-dapp/             harmless connect + sign test page
└── README.md
```

Phantom files may still exist in `extensions/phantom` and `profiles/phantom`
from earlier experiments. They are optional and not part of the template's
crypto flow.

## Safety rules

- Use a **test-only** seed phrase. Treat it as public.
- Never put a seed with real funds in this profile.
- The scripts never read, print, or store the seed phrase. You type it into
  the wallet UI. The profile directory contains the encrypted wallet, just
  like a normal Chrome profile.
- `wallets/extensions/` and `wallets/profiles/` are in `.gitignore`.

## One-time setup

```bash
# 1. Download + unpack MetaMask (already done if the folder exists)
.venv/bin/python scripts/wallet_lib.py install metamask

# 2. Open MetaMask's onboarding in a real browser and import manually
.venv/bin/python scripts/wallet_lib.py setup metamask
```

MetaMask manual import:

1. Click **I have an existing wallet**.
2. Click **Import using Secret Recovery Phrase**.
3. Paste the test seed phrase, then **Continue**.
4. Set the local password to **`123123123`**, accept the terms, and finish.
5. The setup script closes the browser when the wallet home shows an account.

The setup script requires the wallet home (Account + Send/Receive/Swap/Buy),
so it will not mistake an import screen for a finished wallet.

## Check persistence

```bash
.venv/bin/python scripts/wallet_lib.py status
```

`profile_bytes` should be tens of megabytes after the import. Relaunching the
profile must show the account, not the onboarding screen.

## Verify connect + sign

```bash
.venv/bin/python scripts/wallet_verify.py
```

This starts a local test dapp, unlocks the profile, connects, signs a
harmless message, and prints the address and signature. It does **not**
broadcast a transaction.

If the popup selectors change with a MetaMask release, run with `--manual`
and click the prompt yourself.

## Solana

MetaMask supports Solana accounts from the same seed phrase. Solana dapps
discover MetaMask through the Wallet Standard / MetaMask Connect
(`@metamask/connect-solana`), not through `window.ethereum`. The recorder
does not care which chain the dapp uses: when the dapp opens a MetaMask
request, `wallet_approve` approves it on the extension's notification page.

Use `"chain": "solana"` on the action as documentation; the approval helper
uses the same tolerant button list for both chains.

## Use in a video scene

Add `"wallet": "metamask"` to a `page` scene, or set `"wallet": "metamask"`
once in `config/video.json` for every page scene in a crypto demo. A scene can
also use `"crypto": true` as a shorthand for the default MetaMask wallet.

The local test dapp also has a **Send 0 ETH (test)** button. Use it to check
transaction confirmation without writing your own dapp:

```json
{ "action": "wallet_approve", "kind": "transaction", "after": 2.0 }
```

```json
{
  "kind": "page",
  "src": "https://your-dapp.example",
  "wallet": "metamask",
  "chain": "evm",
  "actions": [
    { "action": "click", "sel": "text=Connect" },
    { "action": "wallet_approve", "kind": "connect", "after": 1.0 },
    { "action": "click", "sel": "text=Sign" },
    { "action": "wallet_approve", "kind": "sign", "after": 1.0 },
    { "action": "click", "sel": "text=Send" },
    { "action": "wallet_approve", "kind": "transaction", "after": 2.0 }
  ]
}
```

Actions:

| action | what it does |
|---|---|
| `wallet_unlock` | Unlocks the profile with its local password (`123123123`). |
| `wallet_approve` | Opens the extension's notification page and clicks Connect / Sign / Confirm. `kind`: `connect`, `sign`, `transaction`. |
| `wallet_click` | Waits for a popup, then clicks a specific button by `text`. |
| `wait` | Pauses the recorder so you can approve the popup by hand. |

Wallet scenes unlock automatically before the page opens. Set
`"unlock": false` on the scene if you want to show the lock screen. A scene
can override the password with `"wallet_password": "..."`.

### Why `wallet_approve` opens notification.html

MetaMask's default extension view is a side panel, which Playwright cannot
see. The helper opens `chrome-extension://<id>/notification.html` directly,
where the pending request is displayed, and clicks the button. This works
with both the side panel and popup modes, and avoids duplicate wallet tabs.

The wallet notification page is a separate tab. The main page recording
captures the dapp before/after the approval; the notification page itself is
not in that video. If you want the wallet UI visible on camera, record the
notification page separately and composite it in.

## Troubleshooting

- **No browser window**: setup uses a headed browser. Check `DISPLAY`
  (`echo $DISPLAY`). On a headless server, run under VNC or install Xvfb.
- **Extension not loading**: the scripts use Playwright's bundled Chromium
  (`channel="chromium"`), because Chrome/Edge no longer allow side-loading
  extensions. Do not point them at system Chrome.
- **Wallet opens on onboarding every time**: the import did not finish. Re-run
  `setup`; delete `wallets/profiles/metamask/` only if you want to start over.
- **Wrong seed/account**: delete the profile directory and import again.
- **Popup not approved**: wallet UIs change. Use `wallet_click` with the exact
  button text, or `wallet_verify.py --manual` to inspect the prompt.
- **Phantom**: not required for the template. If you still use it, its
  password is `@hN0pass12` and its onboarding is at `onboarding.html`.
