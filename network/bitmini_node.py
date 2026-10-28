import argparse
import copy
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from flask import Flask, jsonify, request


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def load_private_key(private_hex):
    return ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))


def public_key_hex_from_private(private_hex):
    private_key = load_private_key(private_hex)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return public_key.hex()


def sign_message(private_hex, message):
    private_key = load_private_key(private_hex)
    return private_key.sign(message.encode("utf-8")).hex()


def verify_signature(public_hex, message, signature_hex):
    try:
        key = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
        key.verify(bytes.fromhex(signature_hex), message.encode("utf-8"))
        return True
    except Exception:
        return False


class ChainStore:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.chain_path = os.path.join(self.data_dir, "chain.json")
        self.state_path = os.path.join(self.data_dir, "state.json")
        self.mempool_path = os.path.join(self.data_dir, "mempool.json")
        self.peers_path = os.path.join(self.data_dir, "peers.json")

    def _load_json(self, path, default):
        if not os.path.exists(path):
            return copy.deepcopy(default)
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save_json(self, path, payload):
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        temp = os.path.join(directory, f".{os.path.basename(path)}.{uuid.uuid4().hex}.tmp")

        try:
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            return
        except (OSError, PermissionError):
            try:
                if os.path.exists(temp):
                    os.remove(temp)
            except OSError:
                pass
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())

    def load_chain(self):
        return self._load_json(self.chain_path, [])

    def save_chain(self, chain):
        self._save_json(self.chain_path, chain)

    def load_state(self):
        return self._load_json(self.state_path, {})

    def save_state(self, state):
        self._save_json(self.state_path, state)

    def load_mempool(self):
        return self._load_json(self.mempool_path, [])

    def save_mempool(self, mempool):
        self._save_json(self.mempool_path, mempool)

    def load_peers(self):
        return self._load_json(self.peers_path, [])

    def save_peers(self, peers):
        self._save_json(self.peers_path, sorted(set(peers)))


class BitminiNode:
    def __init__(self, node_id, host, port, data_dir, genesis_path, peer_urls=None):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.store = ChainStore(data_dir)
        self.lock = threading.Lock()
        self._persist_lock = threading.Lock()
        self._persist_scheduled = False

        with open(genesis_path, "r", encoding="utf-8") as handle:
            self.genesis = json.load(handle)

        self.max_supply = float(self.genesis.get("max_supply", 21_000_000.0))
        self.chain_id = self.genesis.get("chain_id", "bitmini-testnet-1")

        self.chain = self.store.load_chain()
        self.state = self.store.load_state()
        self.mempool = self.store.load_mempool()
        self.peer_urls = set(peer_urls or [])
        self.peer_urls.update(self.store.load_peers())
        self.peer_urls.discard(self.base_url)

        if not self.chain or not self.state:
            self._initialize_from_genesis()
        self.sync_with_peers()

    def _persist(self):
        self.store.save_chain(self.chain)
        self.store.save_state(self.state)
        self.store.save_mempool(self.mempool)
        self.store.save_peers(list(self.peer_urls))

    def _schedule_persist(self):
        with self._persist_lock:
            if self._persist_scheduled:
                return
            self._persist_scheduled = True

        worker = threading.Thread(target=self._flush_pending_persist, daemon=True)
        worker.start()

    def _flush_pending_persist(self):
        time.sleep(0.05)
        with self._persist_lock:
            if not self._persist_scheduled:
                return
            self._persist_scheduled = False
        self._persist()

    def _hash_block(self, block):
        payload = dict(block)
        payload.pop("hash", None)
        return sha256_hex(canonical_json(payload))

    def _initialize_from_genesis(self):
        accounts = {}
        validators = []
        minted = 0.0

        for item in self.genesis.get("accounts", []):
            address = str(item["address"])
            balance = float(item.get("balance", 0.0))
            locked = float(item.get("locked_balance", 0.0))
            private_hex = str(item.get("private_key", "")).strip()
            public_hex = str(item.get("public_key", "")).strip()
            if not public_hex and private_hex:
                public_hex = public_key_hex_from_private(private_hex)
            if not public_hex:
                raise ValueError(f"Missing public_key/private_key for account {address}")

            accounts[address] = {
                "balance": balance,
                "locked_balance": locked,
                "nonce": int(item.get("nonce", 0)),
                "public_key": public_hex,
            }
            minted += balance

        for validator in self.genesis.get("validators", []):
            if validator not in accounts:
                raise ValueError(f"Validator {validator} is not a known account")
            validators.append(validator)

        if minted > self.max_supply:
            raise ValueError("Genesis supply exceeds max supply")
        if not validators:
            raise ValueError("At least one validator is required")

        state_root = sha256_hex(canonical_json(accounts))
        genesis_block = {
            "index": 0,
            "timestamp": self.genesis.get("genesis_time", utc_timestamp()),
            "previous_hash": "0",
            "proposer": "genesis",
            "transactions": [
                {"type": "genesis", "memo": "Bitmini genesis", "supply": minted}
            ],
            "state_root": state_root,
            "chain_id": self.chain_id,
            "nonce": 1,
        }
        genesis_block["hash"] = self._hash_block(genesis_block)

        self.chain = [genesis_block]
        self.state = {
            "chain_id": self.chain_id,
            "max_supply": self.max_supply,
            "minted_supply": minted,
            "accounts": accounts,
            "validators": validators,
            "proposer_index": 0,
            "governance_address": str(self.genesis.get("governance_address") or validators[0]),
        }
        self.mempool = []
        self._persist()

    def tx_signing_payload(self, tx):
        payload = {
            "chain_id": tx["chain_id"],
            "sender": tx["sender"],
            "recipient": tx["recipient"],
            "amount": float(tx["amount"]),
            "nonce": int(tx["nonce"]),
            "timestamp": tx["timestamp"],
            "memo": tx.get("memo", ""),
            "type": tx.get("type", "transfer"),
        }
        return canonical_json(payload)

    def sign_transaction(self, tx, private_key_hex):
        return sign_message(private_key_hex, self.tx_signing_payload(tx))

    def sender_pending_nonces(self, sender, current_mempool=None):
        mempool = self.mempool if current_mempool is None else current_mempool
        nonces = []
        for item in mempool:
            if str(item.get("sender", "")) == sender:
                nonce = int(item.get("nonce", -1))
                if nonce >= 0:
                    nonces.append(nonce)
        return sorted(set(nonces))

    def has_pending_nonce(self, sender, nonce, current_mempool=None):
        return int(nonce) in self.sender_pending_nonces(sender, current_mempool=current_mempool)

    def validate_transaction(self, tx, accounts=None):
        working = accounts if accounts is not None else self.state["accounts"]
        required = ["chain_id", "sender", "recipient", "amount", "nonce", "timestamp", "signature"]
        for key in required:
            if key not in tx:
                return False, f"Missing field: {key}"

        if tx["chain_id"] != self.chain_id:
            return False, "Invalid chain ID"
        if tx.get("type", "transfer") != "transfer":
            return False, "Unsupported transaction type"

        sender = str(tx["sender"])
        recipient = str(tx["recipient"])
        if not sender or not recipient:
            return False, "Sender and recipient required"
        if sender == recipient:
            return False, "Self transfer is blocked"

        sender_account = working.get(sender)
        if not sender_account:
            return False, "Sender account not found"

        amount = float(tx["amount"])
        if amount <= 0:
            return False, "Amount must be positive"

        nonce = int(tx["nonce"])
        pending_nonces = self.sender_pending_nonces(
            sender,
            current_mempool=self.mempool if accounts is None else [],
        )
        if nonce in pending_nonces:
            return False, "Duplicate nonce for sender"

        if pending_nonces:
            expected_nonce = pending_nonces[-1] + 1
        else:
            expected_nonce = int(sender_account.get("nonce", 0)) + 1
        if nonce != expected_nonce:
            return False, "Invalid nonce"

        available = float(sender_account.get("balance", 0.0)) - float(sender_account.get("locked_balance", 0.0))
        if amount > available:
            return False, "Insufficient unlocked balance"

        payload = self.tx_signing_payload(tx)
        if not verify_signature(sender_account.get("public_key", ""), payload, tx["signature"]):
            return False, "Invalid signature"

        return True, "ok"

    def apply_transaction(self, tx, accounts):
        sender = str(tx["sender"])
        recipient = str(tx["recipient"])
        amount = float(tx["amount"])

        sender_account = accounts[sender]
        sender_account["balance"] = round(float(sender_account.get("balance", 0.0)) - amount, 8)
        sender_account["nonce"] = int(sender_account.get("nonce", 0)) + 1

        recipient_account = accounts.setdefault(
            recipient,
            {"balance": 0.0, "locked_balance": 0.0, "nonce": 0, "public_key": ""},
        )
        recipient_account["balance"] = round(float(recipient_account.get("balance", 0.0)) + amount, 8)

    def submit_transaction(self, tx, from_peer=False):
        with self.lock:
            ok, reason = self.validate_transaction(tx)
            if not ok:
                return False, reason

            tx_id = sha256_hex(self.tx_signing_payload(tx) + tx["signature"])
            tx["tx_id"] = tx_id
            if any(item.get("tx_id") == tx_id for item in self.mempool):
                return True, "Transaction already pending"

            self.mempool.append(tx)
            self._schedule_persist()

        if not from_peer:
            self.broadcast("/p2p/tx", tx)
        return True, "Transaction accepted"

    def _state_from_chain(self, chain):
        accounts = copy.deepcopy(self.state.get("accounts", {}))
        for block in chain[1:]:
            for tx in block.get("transactions", []):
                sender = str(tx["sender"])
                recipient = str(tx["recipient"])
                amount = float(tx["amount"])
                sender_account = accounts.get(sender)
                if sender_account is None:
                    continue
                sender_account["balance"] = round(float(sender_account.get("balance", 0.0)) - amount, 8)
                sender_account["nonce"] = int(sender_account.get("nonce", 0)) + 1
                recipient_account = accounts.setdefault(
                    recipient,
                    {"balance": 0.0, "locked_balance": 0.0, "nonce": 0, "public_key": ""},
                )
                recipient_account["balance"] = round(float(recipient_account.get("balance", 0.0)) + amount, 8)
        return accounts

    def _is_valid_chain(self, chain):
        if not isinstance(chain, list) or not chain:
            return False
        if int(chain[0].get("index", -1)) != 0:
            return False
        if self._hash_block(chain[0]) != chain[0].get("hash"):
            return False
        if chain[0].get("chain_id") != self.chain_id:
            return False

        accounts = copy.deepcopy(self.state.get("accounts", {}))
        for index in range(1, len(chain)):
            block = chain[index]
            if int(block.get("index", -1)) != index:
                return False
            if block.get("previous_hash") != chain[index - 1].get("hash"):
                return False
            if self._hash_block(block) != block.get("hash"):
                return False
            if block.get("chain_id") != self.chain_id:
                return False
            for tx in block.get("transactions", []):
                ok, reason = self.validate_transaction(tx, accounts=accounts)
                if not ok:
                    return False
                self.apply_transaction(tx, accounts)
            state_root = sha256_hex(canonical_json(accounts))
            if state_root != block.get("state_root"):
                return False
        return True

    def sync_with_peers(self, peer_urls=None):
        peers = list(peer_urls or self.peer_urls)
        best_chain = None

        for peer in peers:
            url = str(peer).strip().rstrip("/")
            if not url:
                continue
            try:
                with urllib.request.urlopen(f"{url}/rpc/chain", timeout=2) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, ValueError):
                continue

            chain = payload.get("blocks") if isinstance(payload, dict) else None
            if not isinstance(chain, list):
                continue
            if len(chain) <= len(self.chain):
                continue
            if not self._is_valid_chain(chain):
                continue
            if best_chain is None or len(chain) > len(best_chain):
                best_chain = chain

        if best_chain is None:
            return False

        self.chain = best_chain
        self.state["accounts"] = self._state_from_chain(best_chain)
        validators = self.state.get("validators", [])
        if validators:
            self.state["proposer_index"] = (len(best_chain) - 1) % len(validators)
        self._persist()
        return True

    def next_proposer(self):
        validators = self.state.get("validators", [])
        if not validators:
            return None
        index = int(self.state.get("proposer_index", 0)) % len(validators)
        return validators[index]

    def mine_block(self, proposer=None):
        with self.lock:
            if not self.mempool:
                return False, "No pending transactions", None

            expected = self.next_proposer()
            if proposer and proposer != expected:
                return False, f"Proposer rotation mismatch. Expected {expected}", None
            proposer = expected

            working_accounts = copy.deepcopy(self.state["accounts"])
            accepted = []
            for tx in self.mempool:
                ok, _ = self.validate_transaction(tx, accounts=working_accounts)
                if not ok:
                    continue
                self.apply_transaction(tx, working_accounts)
                accepted.append(tx)

            if not accepted:
                self.mempool = []
                self._persist()
                return False, "No valid transactions to include", None

            previous = self.chain[-1]
            block = {
                "index": int(previous["index"]) + 1,
                "timestamp": utc_timestamp(),
                "previous_hash": previous["hash"],
                "proposer": proposer,
                "transactions": accepted,
                "state_root": sha256_hex(canonical_json(working_accounts)),
                "chain_id": self.chain_id,
                "nonce": int(previous.get("nonce", 0)) + 1,
            }
            block["hash"] = self._hash_block(block)

            self.chain.append(block)
            self.state["accounts"] = working_accounts
            validators = self.state.get("validators", [])
            if validators:
                self.state["proposer_index"] = (int(self.state.get("proposer_index", 0)) + 1) % len(validators)
            accepted_ids = {item.get("tx_id") for item in accepted}
            self.mempool = [tx for tx in self.mempool if tx.get("tx_id") not in accepted_ids]
            self._persist()

        self.broadcast("/p2p/block", block)
        return True, "Block mined", block

    def validate_and_add_block(self, block, from_peer=False):
        with self.lock:
            if block.get("chain_id") != self.chain_id:
                return False, "Invalid chain ID"
            head = self.chain[-1]
            if int(block.get("index", -1)) != int(head["index"]) + 1:
                return False, "Invalid block index"
            if block.get("previous_hash") != head.get("hash"):
                return False, "Invalid previous hash"
            if self._hash_block(block) != block.get("hash"):
                return False, "Invalid block hash"

            expected = self.next_proposer()
            if expected and block.get("proposer") != expected:
                return False, f"Unexpected proposer. Expected {expected}"

            working_accounts = copy.deepcopy(self.state["accounts"])
            for tx in block.get("transactions", []):
                ok, reason = self.validate_transaction(tx, accounts=working_accounts)
                if not ok:
                    return False, f"Invalid tx in block: {reason}"
                self.apply_transaction(tx, working_accounts)

            expected_root = sha256_hex(canonical_json(working_accounts))
            if expected_root != block.get("state_root"):
                return False, "State root mismatch"

            self.chain.append(block)
            self.state["accounts"] = working_accounts
            validators = self.state.get("validators", [])
            if validators:
                self.state["proposer_index"] = (int(self.state.get("proposer_index", 0)) + 1) % len(validators)
            block_ids = {tx.get("tx_id") for tx in block.get("transactions", [])}
            self.mempool = [tx for tx in self.mempool if tx.get("tx_id") not in block_ids]
            self._persist()

        if not from_peer:
            self.broadcast("/p2p/block", block)
        self.sync_with_peers()
        return True, "Block accepted"

    def governance_payload(self, request_payload):
        data = {
            "chain_id": self.chain_id,
            "governance_address": request_payload["governance_address"],
            "action": request_payload["action"],
            "validator": request_payload["validator"],
            "nonce": int(request_payload["nonce"]),
            "timestamp": request_payload["timestamp"],
        }
        return canonical_json(data)

    def update_validator_set(self, request_payload):
        governance_address = str(request_payload.get("governance_address", "")).strip()
        action = str(request_payload.get("action", "")).strip().lower()
        validator = str(request_payload.get("validator", "")).strip()
        signature = str(request_payload.get("signature", "")).strip()
        nonce = int(request_payload.get("nonce", 0))

        if governance_address != self.state.get("governance_address"):
            return False, "Only governance address can update validators"
        account = self.state.get("accounts", {}).get(governance_address)
        if not account:
            return False, "Governance account not found"
        expected_nonce = int(account.get("nonce", 0)) + 1
        if nonce != expected_nonce:
            return False, "Invalid governance nonce"

        payload = self.governance_payload(request_payload)
        if not verify_signature(account.get("public_key", ""), payload, signature):
            return False, "Invalid governance signature"

        validators = self.state.get("validators", [])
        if action == "add":
            if validator not in self.state.get("accounts", {}):
                return False, "Validator address is not a known account"
            if validator not in validators:
                validators.append(validator)
        elif action == "remove":
            if validator not in validators:
                return False, "Validator not found"
            if len(validators) <= 1:
                return False, "Cannot remove last validator"
            validators = [item for item in validators if item != validator]
        else:
            return False, "Unsupported validator action"

        account["nonce"] = expected_nonce
        self.state["validators"] = validators
        self.state["proposer_index"] = int(self.state.get("proposer_index", 0)) % len(validators)
        self._persist()
        return True, "Validator set updated"

    def create_account(self, address, public_key, initial_balance=0.0, locked_balance=0.0):
        with self.lock:
            acct = self.state["accounts"].get(address)
            if acct:
                return True, "Account already exists"

            initial = float(initial_balance)
            locked = float(locked_balance)
            if initial < 0 or locked < 0 or locked > initial:
                return False, "Invalid initial/locked balances"

            minted = float(self.state.get("minted_supply", 0.0)) + initial
            if minted > self.max_supply:
                return False, "Account funding exceeds max supply"

            self.state["accounts"][address] = {
                "balance": initial,
                "locked_balance": locked,
                "nonce": 0,
                "public_key": public_key,
            }
            self.state["minted_supply"] = minted
            self._persist()
        return True, "Account created"

    def token_metrics(self):
        accounts = self.state.get("accounts", {})
        total_balance = 0.0
        total_locked = 0.0
        for account in accounts.values():
            total_balance += float(account.get("balance", 0.0))
            total_locked += float(account.get("locked_balance", 0.0))
        return {
            "minted": round(total_balance, 8),
            "max": float(self.max_supply),
            "remaining": round(max(self.max_supply - total_balance, 0.0), 8),
            "locked": round(total_locked, 8),
            "circulating": round(total_balance - total_locked, 8),
            "accounts": len(accounts),
            "validators": len(self.state.get("validators", [])),
            "nextProposer": self.next_proposer(),
        }

    def add_peer(self, url):
        peer = str(url or "").strip().rstrip("/")
        if not peer or peer == self.base_url:
            return False
        self.peer_urls.add(peer)
        self._persist()
        return True

    def broadcast(self, path, payload):
        body = json.dumps(payload).encode("utf-8")

        def _deliver(peer):
            req = urllib.request.Request(
                f"{peer}{path}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=1):
                    pass
            except (urllib.error.URLError, TimeoutError, OSError):
                return

        for peer in list(self.peer_urls):
            thread = threading.Thread(target=_deliver, args=(peer,), daemon=True)
            thread.start()


def create_app(node):
    app = Flask(__name__)

    @app.get("/rpc/health")
    def health():
        head = node.chain[-1]
        return jsonify(
            {
                "ok": True,
                "nodeId": node.node_id,
                "chainId": node.chain_id,
                "height": head["index"],
                "headHash": head["hash"],
                "validators": node.state.get("validators", []),
                "nextProposer": node.next_proposer(),
                "peers": sorted(node.peer_urls),
            }
        )

    @app.get("/rpc/chain/head")
    def chain_head():
        return jsonify({"ok": True, "head": node.chain[-1]})

    @app.get("/rpc/chain")
    def chain_dump():
        return jsonify({"ok": True, "count": len(node.chain), "blocks": node.chain})

    @app.get("/rpc/account/<address>")
    def account(address):
        account_data = node.state.get("accounts", {}).get(address)
        if not account_data:
            return jsonify({"ok": False, "error": "Account not found"}), 404
        return jsonify({"ok": True, "account": {"address": address, **account_data}})

    @app.get("/rpc/token-metrics")
    def token_metrics():
        return jsonify({"ok": True, "metrics": node.token_metrics()})

    @app.post("/rpc/account/create")
    def account_create():
        payload = request.get_json(silent=True) or {}
        address = str(payload.get("address", "")).strip()
        public_key = str(payload.get("public_key", "")).strip()
        initial = float(payload.get("initial_balance", 0) or 0)
        locked = float(payload.get("locked_balance", 0) or 0)
        if not address or not public_key:
            return jsonify({"ok": False, "error": "address and public_key are required"}), 400
        ok, message = node.create_account(address, public_key, initial_balance=initial, locked_balance=locked)
        return jsonify({"ok": ok, "message": message}), 200 if ok else 400

    @app.post("/rpc/tx/sign")
    def tx_sign():
        payload = request.get_json(silent=True) or {}
        tx = payload.get("tx") or {}
        private_key = str(payload.get("private_key", "")).strip()
        tx.setdefault("chain_id", node.chain_id)
        tx.setdefault("timestamp", utc_timestamp())
        tx.setdefault("type", "transfer")
        signature = node.sign_transaction(tx, private_key)
        return jsonify({"ok": True, "signature": signature, "tx": tx})

    @app.post("/rpc/tx/submit")
    def tx_submit():
        tx = request.get_json(silent=True) or {}
        ok, message = node.submit_transaction(tx, from_peer=False)
        return jsonify({"ok": ok, "message": message}), 200 if ok else 400

    @app.post("/rpc/block/mine")
    def block_mine():
        payload = request.get_json(silent=True) or {}
        proposer = payload.get("proposer")
        ok, message, block = node.mine_block(proposer=proposer)
        return jsonify({"ok": ok, "message": message, "block": block}), 200 if ok else 400

    @app.post("/rpc/validators/update")
    def validators_update():
        payload = request.get_json(silent=True) or {}
        ok, message = node.update_validator_set(payload)
        return jsonify({"ok": ok, "message": message, "validators": node.state.get("validators", [])}), 200 if ok else 400

    @app.post("/p2p/peers/add")
    def peer_add():
        payload = request.get_json(silent=True) or {}
        added = node.add_peer(payload.get("url"))
        return jsonify({"ok": True, "added": added, "peers": sorted(node.peer_urls)})

    @app.post("/p2p/tx")
    def peer_tx():
        tx = request.get_json(silent=True) or {}
        ok, message = node.submit_transaction(tx, from_peer=True)
        return jsonify({"ok": ok, "message": message}), 200 if ok else 400

    @app.post("/p2p/block")
    def peer_block():
        block = request.get_json(silent=True) or {}
        ok, message = node.validate_and_add_block(block, from_peer=True)
        return jsonify({"ok": ok, "message": message}), 200 if ok else 400

    return app


def parse_args():
    parser = argparse.ArgumentParser(description="Bitmini sovereign node (Phase 1 MVP)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=9101, type=int)
    parser.add_argument("--node-id", default="node-a")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--genesis", default=os.path.join(os.path.dirname(__file__), "genesis.json"))
    parser.add_argument("--peer", action="append", default=[])
    return parser.parse_args()


def main():
    args = parse_args()
    data_dir = args.data_dir or os.path.join(os.path.dirname(__file__), "data", args.node_id)
    node = BitminiNode(
        node_id=args.node_id,
        host=args.host,
        port=args.port,
        data_dir=data_dir,
        genesis_path=args.genesis,
        peer_urls=args.peer,
    )
    app = create_app(node)
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
