#!/usr/bin/env python3
"""Injected wallet: a pre-connected account from a local private key.

The extension flow (`wallet_lib.py`) puts a real MetaMask profile in the
browser, which means the recording films a connect prompt, a signature prompt
and a transaction prompt. For a product demo that is dead screen time: the
viewer learns nothing from a popup, and the product is off screen.

This module injects an EIP-1193 provider and a Solana wallet-standard wallet
that are already connected, so the demo can skip the connect step and stay on
the product. Signatures are real, produced with the key from `.env`. A
transaction is signed for real and broadcast only when `WALLET_BROADCAST=1`
and an RPC URL is configured.

Keys are read from (later wins) `wallets/.env`, the repo `.env`, the project
`.env`, then the process environment. Only test keys belong in those files;
`.env.example` shows the names.

CLI:
    python scripts/wallet_inject.py --check      derive + sign, print nothing secret
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

MODES = ("inject", "injected", "key", "private-key")

# Which key name fills which chain. PRIVATE_KEY is the convenience alias; the
# chain-specific name wins when both are present.
KEY_NAMES = {
    "evm": ("EVM_PRIVATE_KEY", "PRIVATE_KEY"),
    "sol": ("SOL_PRIVATE_KEY", "SOLANA_PRIVATE_KEY"),
}

RPC_NAMES = {
    "evm": ("EVM_RPC_URL", "RPC_URL"),
    "sol": ("SOL_RPC_URL", "SOLANA_RPC_URL", "RPC_URL"),
}

_ENV_LOADED = False


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------

def _template():
    return lib.TEMPLATE


def _env_candidates():
    tpl = _template()
    out = [tpl / "wallets" / ".env", tpl / ".env"]
    if getattr(lib, "ROOT", None):
        out.append(Path(lib.ROOT) / ".env")
    return out


def load_env():
    """Read .env files without clobbering the process environment."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    preset = dict(os.environ)
    values = {}
    for path in _env_candidates():
        try:
            text = path.read_text()
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val:
                values[key] = val
    for key, val in values.items():
        if key not in preset:
            os.environ[key] = val


def _first(names):
    for name in names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


def evm_key():
    load_env()
    return _first(KEY_NAMES["evm"])


def sol_key():
    load_env()
    return _first(KEY_NAMES["sol"])


def evm_rpc():
    load_env()
    return _first(RPC_NAMES["evm"])


def sol_rpc():
    load_env()
    return _first(RPC_NAMES["sol"])


def broadcast_enabled():
    load_env()
    return os.environ.get("WALLET_BROADCAST", "").strip().lower() in (
        "1", "true", "yes", "on")


def keys_available():
    return bool(evm_key() or sol_key())


def fingerprint_env():
    """Stable value for the clip cache; changes when the demo account does."""
    import hashlib
    load_env()
    parts = []
    evm, sol = evm_key(), sol_key()
    if evm:
        try:
            from eth_account import Account
            parts.append(Account.from_key(evm).address)
        except ImportError:
            parts.append("evm")
    if sol:
        try:
            from solders.keypair import Keypair
            parts.append(str(Keypair.from_base58_string(sol).pubkey()))
        except ImportError:
            parts.append("sol")
    parts.append(os.environ.get("EVM_CHAIN_ID", ""))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


# --------------------------------------------------------------------------
# signing
# --------------------------------------------------------------------------

MISSING_EVM = ("EVM signing needs eth-account:\n"
               "  ./scripts/setup.sh --wallet      (or)\n"
               "  uv pip install -r requirements-wallet.txt --python .venv")
MISSING_SOL = ("Solana signing needs solders:\n"
               "  ./scripts/setup.sh --wallet      (or)\n"
               "  uv pip install -r requirements-wallet.txt --python .venv")


def _eth_account():
    try:
        from eth_account import Account  # noqa: F401
        return Account
    except ImportError:
        sys.exit(MISSING_EVM)


def _solders():
    try:
        from solders.keypair import Keypair  # noqa: F401
        return Keypair
    except ImportError:
        sys.exit(MISSING_SOL)


def _int(value, default=0):
    if value is None or value == "":
        return default
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def _hexbytes(value):
    value = value if isinstance(value, str) else "0x" + bytes(value).hex()
    return value if value.startswith("0x") else "0x" + value


class Wallet:
    """Accounts derived from the configured keys, plus the calls a page makes."""

    def __init__(self, evm=None, sol=None, evm_rpc_url="", sol_rpc_url="",
                 chain_id=None, broadcast=False):
        self.evm = evm
        self.sol = sol
        self.chain_id = int(chain_id or 1)
        self.evm_rpc_url = evm_rpc_url
        self.sol_rpc_url = sol_rpc_url
        self.broadcast = broadcast
        self._evm_account = None
        self._sol_keypair = None

    # -- construction ------------------------------------------------------

    @classmethod
    def from_env(cls, chain="evm", chain_id=None):
        load_env()
        wallet = cls(
            evm=evm_key() or None,
            sol=sol_key() or None,
            evm_rpc_url=evm_rpc(),
            sol_rpc_url=sol_rpc(),
            chain_id=chain_id or os.environ.get("EVM_CHAIN_ID") or 1,
            broadcast=broadcast_enabled(),
        )
        if chain in ("evm", "ethereum") and not wallet.evm:
            wallet.fail_evm()
        if chain in ("sol", "solana") and not wallet.sol:
            wallet.fail_sol()
        return wallet

    @staticmethod
    def fail_evm():
        sys.exit("wallet: no EVM key. Put EVM_PRIVATE_KEY in wallets/.env "
                 "(see wallets/.env.example) or use \"wallet\": \"metamask\".\n"
                 "Ask the user for a TEST-ONLY key; never invent one.")

    @staticmethod
    def fail_sol():
        sys.exit("wallet: no Solana key. Put SOL_PRIVATE_KEY in wallets/.env "
                 "(see wallets/.env.example) or use \"wallet\": \"metamask\".\n"
                 "Ask the user for a TEST-ONLY key; never invent one.")

    # -- accounts ----------------------------------------------------------

    @property
    def evm_account(self):
        if self._evm_account is None:
            Account = _eth_account()
            self._evm_account = Account.from_key(self.evm)
        return self._evm_account

    @property
    def sol_keypair(self):
        if self._sol_keypair is None:
            Keypair = _solders()
            self._sol_keypair = Keypair.from_base58_string(self.sol)
        return self._sol_keypair

    @property
    def evm_address(self):
        return self.evm_account.address if self.evm else None

    @property
    def sol_address(self):
        return str(self.sol_keypair.pubkey()) if self.sol else None

    def fingerprint(self):
        """Short, non-secret value for the clip cache."""
        import hashlib
        blob = f"{self.evm_address}|{self.sol_address}|{self.chain_id}"
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    # -- chain metadata ----------------------------------------------------

    def resolve_chain_id(self):
        if not self.evm:
            return self.chain_id
        env_id = os.environ.get("EVM_CHAIN_ID")
        if env_id:
            return _int(env_id, self.chain_id)
        if self.evm_rpc_url:
            try:
                return _int(self.rpc("eth_chainId", [], url=self.evm_rpc_url))
            except Exception:
                pass
        return self.chain_id

    def sol_cluster(self):
        url = (self.sol_rpc_url or "").lower()
        if "devnet" in url:
            return "devnet"
        if "testnet" in url:
            return "testnet"
        return "mainnet-beta"

    # -- RPC ---------------------------------------------------------------

    def rpc(self, method, params, url=None):
        target = url or self.evm_rpc_url
        if not target:
            raise RuntimeError(
                f"{method} needs an RPC. Set EVM_RPC_URL in wallets/.env.")
        body = json.dumps({"jsonrpc": "2.0", "id": 1,
                           "method": method, "params": params}).encode()
        req = urllib.request.Request(
            target, data=body, headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                payload = json.loads(res.read())
        except urllib.error.URLError as exc:
            raise RuntimeError(f"rpc {method} failed: {exc}") from exc
        if payload.get("error"):
            err = payload["error"]
            raise RuntimeError(f"rpc {method}: {err.get('message', err)}")
        return payload.get("result")

    # -- dispatch ----------------------------------------------------------

    def handle(self, payload):
        """One call from the page. Always returns JSON, never raises."""
        if isinstance(payload, str):
            payload = json.loads(payload)
        method = (payload or {}).get("method", "")
        params = (payload or {}).get("params") or []
        try:
            result = getattr(self, "_" + method, None)
            if result is None:
                result = self._proxy(method, params)
            else:
                result = result(params)
            return {"result": result}
        except Exception as exc:  # surfaced as a rejected promise in the page
            return {"error": {"message": str(exc)[:400], "code": -32603}}

    # EIP-1193 -------------------------------------------------------------

    def _accounts(self, params):
        return [self.evm_address] if self.evm else []

    def _eth_chain_id(self, params):
        return hex(self.resolve_chain_id())

    def _personal_sign(self, params):
        data, _address = params[0], params[1] if len(params) > 1 else None
        from eth_account.messages import encode_defunct
        msg = (encode_defunct(hexstr=data) if str(data).startswith("0x")
               else encode_defunct(text=str(data)))
        signed = self.evm_account.sign_message(msg)
        return "0x" + signed.signature.hex().removeprefix("0x")

    def _eth_sign_typed_data(self, params):
        data = params[1] if len(params) > 1 else params[0]
        from eth_account.messages import encode_typed_data
        typed = json.loads(data) if isinstance(data, str) else data
        signed = self.evm_account.sign_message(
            encode_typed_data(full_message=typed))
        return "0x" + signed.signature.hex().removeprefix("0x")

    def _eth_send_transaction(self, params):
        tx = dict(params[0])
        tx.pop("from", None)
        if not self.broadcast:
            raise RuntimeError(
                "wallet is injected read/sign only: a transaction was requested "
                "but WALLET_BROADCAST is not set. Add WALLET_BROADCAST=1 to "
                "wallets/.env only if this demo must send a real transaction.")
        if not self.evm_rpc_url:
            raise RuntimeError("eth_sendTransaction needs EVM_RPC_URL.")
        tx.setdefault("chainId", self.resolve_chain_id())
        if tx.get("nonce") is None:
            tx["nonce"] = _int(self.rpc("eth_getTransactionCount",
                                        [self.evm_address, "pending"]))
        if tx.get("gas") is None:
            tx["gas"] = _int(self.rpc("eth_estimateGas", [{
                "from": self.evm_address,
                "to": tx.get("to"),
                "value": tx.get("value", "0x0"),
                "data": tx.get("data") or tx.get("input") or "0x",
            }]))
        if tx.get("maxFeePerGas") is None and tx.get("gasPrice") is None:
            tx["maxFeePerGas"] = _int(self.rpc("eth_maxPriorityFeePerGas", [])) * 2
            tx["maxPriorityFeePerGas"] = _int(
                self.rpc("eth_maxPriorityFeePerGas", []))
        tx["chainId"] = _int(tx["chainId"])
        for key in ("nonce", "gas", "value", "gasPrice",
                    "maxFeePerGas", "maxPriorityFeePerGas"):
            if isinstance(tx.get(key), str):
                tx[key] = _int(tx[key])
        signed = self.evm_account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        return self.rpc("eth_sendRawTransaction", ["0x" + raw.hex().removeprefix("0x")])

    def _proxy(self, method, params):
        """Read-only calls (eth_call, eth_getBalance, ...) go to the RPC."""
        if method.startswith(("eth_", "net_", "web3_")):
            return self.rpc(method, params)
        raise RuntimeError(f"method {method} is not supported by the injected wallet")

    # Solana ---------------------------------------------------------------

    def _sol_sign_message(self, params):
        raw = base64.b64decode(params["message"])
        signature = self.sol_keypair.sign_message(raw)
        return {"signature": base64.b64encode(bytes(signature)).decode(),
                "signedMessage": params["message"]}

    def _sol_sign_transaction(self, params):
        from solders.transaction import VersionedTransaction
        raw = base64.b64decode(params["transaction"])
        tx = VersionedTransaction.from_bytes(raw)
        tx.sign([self.sol_keypair])
        return {"signedTransaction": base64.b64encode(bytes(tx)).decode()}

    def _sol_sign_and_send(self, params):
        signed = self._sol_sign_transaction(params)
        if not self.broadcast:
            raise RuntimeError(
                "wallet is injected read/sign only: signAndSend needs "
                "WALLET_BROADCAST=1 and SOL_RPC_URL.")
        if not self.sol_rpc_url:
            raise RuntimeError("signAndSend needs SOL_RPC_URL.")
        result = self.rpc("sendTransaction",
                          [signed["signedTransaction"], {"encoding": "base64"}],
                          url=self.sol_rpc_url)
        return {"signature": result}


# --------------------------------------------------------------------------
# page script
# --------------------------------------------------------------------------

WALLET_JS = r"""
(() => {
  const CFG = __CONFIG__;
  if (!CFG.evm && !CFG.sol) return;
  const bridge = (method, params) => {
    if (!window.__demo_wallet_call) {
      return Promise.reject(new Error('demo wallet bridge missing'));
    }
    return window.__demo_wallet_call({ method, params })
      .then((r) => {
        if (r && r.error) {
          const err = new Error(r.error.message || 'wallet error');
          err.code = r.error.code;
          throw err;
        }
        return r.result;
      });
  };
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

  /* ---- EVM (EIP-1193 + EIP-6963) ---- */
  if (CFG.evm) {
    const listeners = Object.create(null);
    const emit = (name, ...args) => {
      (listeners[name] || []).forEach((fn) => {
        try { fn(...args); } catch (e) { /* a bad listener must not break the page */ }
      });
    };
    const provider = {
      isMetaMask: true,
      isDemoWallet: true,
      chainId: CFG.evm.chainId,
      networkVersion: String(parseInt(CFG.evm.chainId, 16)),
      selectedAddress: CFG.evm.address,
      on(name, fn) { (listeners[name] = listeners[name] || []).push(fn); return provider; },
      removeListener(name, fn) {
        listeners[name] = (listeners[name] || []).filter((f) => f !== fn);
        return provider;
      },
      off(name, fn) { return provider.removeListener(name, fn); },
      isConnected() { return true; },
      request({ method, params }) {
        switch (method) {
          case 'eth_accounts':
            return Promise.resolve([CFG.evm.address]);
          case 'eth_requestAccounts':
          case 'wallet_requestPermissions':
            setTimeout(() => emit('accountsChanged', [CFG.evm.address]), 0);
            if (method === 'wallet_requestPermissions') {
              return Promise.resolve([{ parentCapability: 'eth_accounts' }]);
            }
            return Promise.resolve([CFG.evm.address]);
          case 'wallet_getPermissions':
            return Promise.resolve([{ parentCapability: 'eth_accounts' }]);
          case 'eth_chainId':
            return Promise.resolve(CFG.evm.chainId);
          case 'net_version':
            return Promise.resolve(String(parseInt(CFG.evm.chainId, 16)));
          case 'wallet_switchEthereumChain':
            return String((params && params[0] && params[0].chainId) || '')
              .toLowerCase() === CFG.evm.chainId
              ? Promise.resolve(null)
              : Promise.reject(Object.assign(
                  new Error('chain not available in the demo wallet'), { code: 4902 }));
          case 'personal_sign':
            return bridge('personal_sign', params);
          case 'eth_sign':
            return bridge('personal_sign', [params[1], params[0]]);
          case 'eth_signTypedData':
          case 'eth_signTypedData_v3':
          case 'eth_signTypedData_v4':
            return bridge('eth_sign_typed_data', params);
          case 'eth_sendTransaction':
            return bridge('eth_send_transaction', params);
          default:
            return bridge('proxy', [method, params]);
        }
      },
    };
    /* Some dapps still look for these. */
    provider.enable = () => provider.request({ method: 'eth_requestAccounts' });
    provider.send = (payload, cb) => {
      const p = provider.request(payload);
      if (cb) { p.then((r) => cb(null, r), (e) => cb(e)); return undefined; }
      return p;
    };
    provider.sendAsync = provider.send;

    Object.defineProperty(window, 'ethereum', {
      value: provider, configurable: true, writable: false,
    });
    window.dispatchEvent(new Event('ethereum#initialized'));

    const info = {
      uuid: 'a7c1f2d4-3e61-4b58-9d0a-demo00000001',
      name: CFG.name || 'Demo Wallet',
      icon: CFG.icon,
      rdns: 'dev.demo.wallet',
    };
    const announce = () => window.dispatchEvent(new CustomEvent(
      'eip6963:announceProvider', { detail: { info, provider } }));
    window.addEventListener('eip6963:requestProvider', announce);
    announce();
    document.addEventListener('DOMContentLoaded', announce);
    setTimeout(() => emit('connect', { chainId: CFG.evm.chainId }), 0);
  }

  /* ---- Solana (wallet standard) ---- */
  if (CFG.sol) {
    const chains = CFG.sol.chains;
    const account = {
      address: CFG.sol.address,
      publicKey: b64(CFG.sol.publicKey),
      chains,
      features: [
        'standard:connect', 'standard:disconnect', 'standard:events',
        'solana:signMessage', 'solana:signTransaction',
        'solana:signAndSendTransaction',
      ],
      label: 'Demo Wallet',
    };
    /* Wallet-standard features are variadic: (...inputs) => outputs[]. */
    const feature = (body) => Object.assign(
      { version: '1.0.0', supportedTransactionVersions: ['legacy', 0] }, body);
    const wallet = {
      version: '1.0.0',
      name: CFG.name || 'Demo Wallet',
      icon: CFG.icon,
      chains,
      accounts: [account],
      features: Object.assign(
        {
          'standard:connect': { version: '1.0.0',
            connect: () => Promise.resolve({ accounts: [account] }) },
          'standard:disconnect': { version: '1.0.0',
            disconnect: () => Promise.resolve() },
          'standard:events': { version: '1.0.0',
            on: () => () => {} },
        },
        {
          'solana:signMessage': feature({
            signMessage: (...inputs) => Promise.all(inputs.map(async ({ message }) => {
              const r = await bridge('sol_sign_message',
                { message: btoa(String.fromCharCode(...new Uint8Array(message))) });
              return { signedMessage: b64(r.signedMessage),
                       signature: b64(r.signature) };
            })),
          }),
          'solana:signTransaction': feature({
            signTransaction: (...inputs) => Promise.all(inputs.map(async ({ transaction }) => {
              const r = await bridge('sol_sign_transaction',
                { transaction: btoa(String.fromCharCode(...new Uint8Array(transaction))) });
              return { signedTransaction: b64(r.signedTransaction) };
            })),
          }),
          'solana:signAndSendTransaction': feature({
            signAndSendTransaction: (...inputs) => Promise.all(inputs.map(async ({ transaction }) => {
              const r = await bridge('sol_sign_and_send',
                { transaction: btoa(String.fromCharCode(...new Uint8Array(transaction))) });
              return { signature: b64(r.signature) };
            })),
          }),
        },
      ),
    };
    const announce = (register) => {
      try { register(wallet); } catch (e) { /* app rejected the wallet */ }
    };
    window.addEventListener('wallet-standard:register-wallet', (event) => {
      if (typeof event.detail === 'function') announce(event.detail);
    });
    window.addEventListener('wallet-standard:app-ready', (event) => {
      const api = event.detail;
      if (api && typeof api.register === 'function') api.register(announce);
    });
  }
})();
"""

ICON = ("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmci"
        "IHZpZXdCb3g9IjAgMCAzMiAzMiI+PHJlY3Qgd2lkdGg9IjMyIiBoZWlnaHQ9IjMyIiByeD0i"
        "OCIgZmlsbD0iIzM0ZDM5OSIvPjwvc3ZnPg==")


def init_script(wallet):
    cfg = {
        "name": os.environ.get("DEMO_WALLET_NAME", "Demo Wallet"),
        "icon": ICON,
        "evm": None,
        "sol": None,
    }
    if wallet.evm:
        chain_id = wallet.resolve_chain_id()
        cfg["evm"] = {"address": wallet.evm_address,
                      "chainId": hex(chain_id)}
    if wallet.sol:
        public_key = bytes(wallet.sol_keypair.pubkey())
        cfg["sol"] = {
            "address": wallet.sol_address,
            "publicKey": base64.b64encode(public_key).decode(),
            "chains": [f"solana:{wallet.sol_cluster()}"],
        }
    return WALLET_JS.replace("__CONFIG__", json.dumps(cfg))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="derive addresses and sign a test message")
    args = ap.parse_args()
    lib.init(None)
    load_env()
    evm, sol = evm_key(), sol_key()
    if not evm and not sol:
        sys.exit("no EVM_PRIVATE_KEY / SOL_PRIVATE_KEY in wallets/.env, .env, "
                 "or the environment (see wallets/.env.example)")
    wallet = Wallet(evm=evm or None, sol=sol or None,
                    evm_rpc_url=evm_rpc(), sol_rpc_url=sol_rpc(),
                    chain_id=os.environ.get("EVM_CHAIN_ID") or 1,
                    broadcast=broadcast_enabled())
    if evm:
        print(f"evm  {wallet.evm_address}  chain {wallet.resolve_chain_id()}")
        sig = wallet.handle({"method": "personal_sign",
                             "params": ["0x" + b"hello demo".hex(),
                                        wallet.evm_address]})
        print(f"     sign  {'ok' if 'result' in sig else sig['error']['message']}")
    if sol:
        print(f"sol  {wallet.sol_address}  {wallet.sol_cluster()}")
        msg = base64.b64encode(b"hello demo").decode()
        sig = wallet.handle({"method": "sol_sign_message",
                             "params": {"message": msg}})
        print(f"     sign  {'ok' if 'result' in sig else sig['error']['message']}")
    print(f"rpc  evm={'set' if wallet.evm_rpc_url else 'unset'}  "
          f"sol={'set' if wallet.sol_rpc_url else 'unset'}  "
          f"broadcast={'on' if wallet.broadcast else 'off'}")


if __name__ == "__main__":
    main()
