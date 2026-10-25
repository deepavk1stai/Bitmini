#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

spec = importlib.util.spec_from_file_location("bitmini_node_module", Path(__file__).resolve().with_name("bitmini_node.py"))
bitmini_node_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bitmini_node_module)
canonical_json = bitmini_node_module.canonical_json
sign_message = bitmini_node_module.sign_message

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
NODE_SCRIPT = ROOT / "network" / "bitmini_node.py"


def private_key_hex():
    private = ed25519.Ed25519PrivateKey.generate()
    return private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()


def public_key_hex_from_private(private_hex):
    private = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return public.hex()


def generate_devnet_genesis(validator_count=3):
    accounts = []
    validators = []
    for index in range(validator_count):
        private_hex = private_key_hex()
        public_hex = public_key_hex_from_private(private_hex)
        label = f"BDEV{index:02d}{secrets.token_hex(6).upper()}"
        balance = 1_000_000.0
        locked = 500_000.0
        accounts.append(
            {
                "address": label,
                "balance": balance,
                "locked_balance": locked,
                "nonce": 0,
                "private_key": private_hex,
                "public_key": public_hex,
            }
        )
        validators.append(label)
    genesis = {
        "chain_id": "bitmini-devnet-1",
        "max_supply": 21_000_000.0,
        "genesis_time": "2026-10-24T00:00:00Z",
        "governance_address": validators[0],
        "validators": validators,
        "accounts": accounts,
    }
    return genesis


def write_genesis(path, genesis):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(genesis, indent=2), encoding="utf-8")
    return path


def wait_for_health(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/rpc/health", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if payload.get("ok"):
                    return payload
        except Exception:
            time.sleep(0.5)
    raise TimeoutError(f"Node did not become healthy at {url}")


def post_json(url, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(f"{url}{path}", data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8") or "{}"
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") or "{}"
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"error": body}


def start_node(processes, node_id, port, genesis_path, peer_urls):
    cmd = [sys.executable, str(NODE_SCRIPT), "--host", "127.0.0.1", "--port", str(port), "--node-id", node_id, "--data-dir", str(ROOT / "network" / "data" / node_id), "--genesis", str(genesis_path)]
    for peer in peer_urls:
        cmd.extend(["--peer", peer])
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    processes.append(proc)
    url = f"http://127.0.0.1:{port}"
    health = wait_for_health(url)
    return url, health


def main():
    parser = argparse.ArgumentParser(description="Start a local Bitmini PoS devnet with three validators.")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--base-port", type=int, default=9101)
    parser.add_argument("--duration", type=int, default=0)
    parser.add_argument("--auto-mine", action="store_true")
    args = parser.parse_args()

    if args.count < 2:
        raise SystemExit("Devnet requires at least 2 nodes.")

    genesis = generate_devnet_genesis(args.count)
    work_dir = ROOT / "network" / "tmp-devnet"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    genesis_path = write_genesis(work_dir / "genesis-devnet.json", genesis)

    data_root = ROOT / "network" / "data"
    if data_root.exists():
        shutil.rmtree(data_root)
    data_root.mkdir(parents=True, exist_ok=True)

    processes = []
    urls = []
    for index in range(args.count):
        port = args.base_port + index
        peers = [f"http://127.0.0.1:{args.base_port + other}" for other in range(args.count) if other != index]
        url, _ = start_node(processes, f"node-{index + 1}", port, genesis_path, peers)
        urls.append(url)

    print("Bitmini local PoS devnet ready.")
    for url in urls:
        metadata = wait_for_health(url)
        print(f" - {url} :: {metadata.get('chainId')} :: next proposer {metadata.get('nextProposer')}")

    if args.auto_mine:
        sender = genesis["validators"][0]
        recipient = genesis["validators"][1]
        sender_key = next(item["private_key"] for item in genesis["accounts"] if item["address"] == sender)
        tx = {
            "chain_id": genesis["chain_id"],
            "sender": sender,
            "recipient": recipient,
            "amount": 10.0,
            "nonce": 1,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "memo": "devnet bootstrap transfer",
            "type": "transfer",
        }
        tx["signature"] = sign_message(sender_key, canonical_json(tx))
        status, response = post_json(urls[0], "/rpc/tx/submit", tx)
        print(f"tx-submit :: {status} :: {response}")
        status, response = post_json(urls[0], "/rpc/block/mine", {"proposer": sender})
        print(f"auto-mine :: {status} :: {response}")

    if args.duration > 0:
        time.sleep(args.duration)
    else:
        print("Press Ctrl+C to stop the devnet.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    for proc in processes:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
