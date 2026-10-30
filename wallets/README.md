# Wallets for crypto demos

Two ways to give a dapp a wallet during recording:

| mode | on camera | use it for |
|---|---|---|
| **inject** (default) | nothing - the account is already connected | every product demo; the viewer sees the app, not a popup |
| metamask | the real connect / sign / confirm prompts | demos of the wallet flow itself; a user who will not share a key |

Both are test-only. The injected mode signs with a key from `wallets/.env`;
the extension mode imports a seed into a throwaway browser profile. Never put
a key or seed with real funds in either one.

```
wallets/
├── .env                   test keys, gitignored (.env.example is committed)
├── inject-dapp/           connect + sign check page for the injected wallet
├── extensions/metamask/   unpacked extension (gitignored)
├── profiles/metamask/     persistent Chromium profile (gitignored)
├── test-dapp/             check page for the extension wallet
└── README.md
```

## Injected wallet

```
wallets/.env
  EVM_PRIVATE_KEY=     0x + 64 hex
  SOL_PRIVATE_KEY=     base58 secret key (the 64-byte keypair)
  EVM_RPC_URL=         optional; reads and chain id
  SOL_RPC_URL=         optional; Solana signAndSendTransaction
  EVM_CHAIN_ID=        optional fallback, 1 = mainnet
  WALLET_BROADCAST=0   leave 0 unless the demo sends a real transaction
```

Ask the user for the key; do not generate one for them. The address shows up
in the video, so it has to be an account they are happy to publish.

```bash
cp wallets/.env.example wallets/.env     # fill in by hand
./scripts/setup.sh --wallet              # eth-account + solders
.venv/bin/python scripts/wallet_inject.py --check        # derive + sign, no browser
.venv/bin/python scripts/wallet_inject_check.py          # real browser, EVM + Solana
```

In a story, set `"wallet": "inject"` on the scene, or on the whole video in
`config/video.json`. The provider is installed before the page loads and
answers `eth_accounts` with the configured account, so there is no connect
step to film. `personal_sign` and `eth_signTypedData_v4` return real
signatures. Transactions are signed but only broadcast when
`WALLET_BROADCAST=1` and an RPC URL are set.

Scripts written for the extension flow keep working: `wallet_approve`,
`wallet_unlock` and `wallet_click` actions are skipped when the wallet is
injected.

Limits: the shim covers the common EIP-1193 calls and the Solana wallet
standard features. A dapp that needs a vendor-specific API (MetaMask
multichain `wallet_*` extensions, WalletConnect sessions) still needs the
extension flow.

## MetaMask profile (extension mode)

A real MetaMask extension in a **persistent Playwright profile**. Import a
test seed once and the wallet survives every recording run.

MetaMask holds EVM accounts and Solana accounts from the same seed, so one
profile covers both.

Phantom files may still exist in `extensions/phantom` and `profiles/phantom`
from earlier experiments. They are optional and not part of the template's
crypto flow.

## Safety rules

- Use a **test-only** key and seed. Treat both as public: the address is on
  camera and the key sits in a file on disk.
- Never put a key or seed with real funds in `wallets/.env` or in the profile.
- `wallets/.env`, `wallets/extensions/` and `wallets/profiles/` are in
  `.gitignore`. Check `git check-ignore -v wallets/.env` after touching the
  ignore rules.
- The extension scripts never read, print, or store the seed phrase. You type
  it into the wallet UI; the profile directory holds the encrypted wallet,
  like a normal Chrome profile.
- `wallet_inject.py --check` prints addresses only. Keep it that way when you
  add logging: a key in a terminal log ends up in a screenshot.

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
