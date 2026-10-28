import json
import tempfile
import threading
import time
import urllib.error
from pathlib import Path

from werkzeug.serving import make_server

from network.bitmini_node import BitminiNode, create_app, utc_timestamp


def make_genesis(path: Path):
    payload = {
        "chain_id": "bitmini-testnet-local",
        "max_supply": 21000000,
        "genesis_time": "2026-10-04T00:00:00Z",
        "governance_address": "BRESERVE",
        "validators": ["BRESERVE"],
        "accounts": [
            {
                "address": "BRESERVE",
                "balance": 1000000.0,
                "locked_balance": 1000000.0,
                "nonce": 0,
                "private_key": "1f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100",
            },
            {
                "address": "BALICE",
                "balance": 100.0,
                "locked_balance": 20.0,
                "nonce": 0,
                "private_key": "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100",
            },
            {
                "address": "BBOB",
                "balance": 5.0,
                "locked_balance": 0.0,
                "nonce": 0,
                "private_key": "3f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100",
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def build_tx(node, sender, recipient, amount, nonce, private_key):
    tx = {
        "chain_id": node.chain_id,
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "nonce": nonce,
        "timestamp": utc_timestamp(),
        "memo": "test",
        "type": "transfer",
    }
    tx["signature"] = node.sign_transaction(tx, private_key)
    return tx


def test_node_initializes_from_genesis_and_metrics():
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)

        node = BitminiNode(
            node_id="n1",
            host="127.0.0.1",
            port=9201,
            data_dir=str(Path(temp_dir) / "data"),
            genesis_path=str(genesis),
            peer_urls=[],
        )

        assert len(node.chain) == 1
        metrics = node.token_metrics()
        assert metrics["max"] == 21000000.0
        assert metrics["locked"] == 1000020.0
        assert metrics["circulating"] == 85.0
        assert metrics["nextProposer"] == "BRESERVE"


def test_locked_balance_blocks_overspending():
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)
        node = BitminiNode(
            node_id="n2",
            host="127.0.0.1",
            port=9202,
            data_dir=str(Path(temp_dir) / "data"),
            genesis_path=str(genesis),
            peer_urls=[],
        )

        tx = build_tx(node, "BALICE", "BBOB", 81.0, 1, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        ok, reason = node.validate_transaction(tx)
        assert ok is False
        assert "unlocked" in reason.lower()


def test_submit_transaction_and_mine_block_updates_state():
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)
        node = BitminiNode(
            node_id="n3",
            host="127.0.0.1",
            port=9203,
            data_dir=str(Path(temp_dir) / "data"),
            genesis_path=str(genesis),
            peer_urls=[],
        )

        tx = build_tx(node, "BALICE", "BBOB", 10.0, 1, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        ok, message = node.submit_transaction(tx)
        assert ok is True
        assert "accepted" in message.lower() or "pending" in message.lower()

        mined, _, block = node.mine_block("BRESERVE")
        assert mined is True
        assert block["index"] == 1
        assert block["proposer"] == "BRESERVE"

        alice = node.state["accounts"]["BALICE"]
        bob = node.state["accounts"]["BBOB"]
        assert alice["balance"] == 90.0
        assert alice["nonce"] == 1
        assert bob["balance"] == 15.0


def test_validator_governance_and_rotation():
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)
        node = BitminiNode(
            node_id="n4",
            host="127.0.0.1",
            port=9204,
            data_dir=str(Path(temp_dir) / "data"),
            genesis_path=str(genesis),
            peer_urls=[],
        )

        payload = {
            "governance_address": "BRESERVE",
            "action": "add",
            "validator": "BALICE",
            "nonce": 1,
            "timestamp": utc_timestamp(),
        }
        signature = node.sign_transaction(
            {
                "chain_id": node.chain_id,
                "sender": payload["governance_address"],
                "recipient": payload["validator"],
                "amount": 0,
                "nonce": payload["nonce"],
                "timestamp": payload["timestamp"],
                "memo": payload["action"],
                "type": "transfer",
            },
            "1f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100",
        )
        governance_payload = node.governance_payload(payload)
        from network.bitmini_node import sign_message
        payload["signature"] = sign_message("1f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100", governance_payload)

        ok, message = node.update_validator_set(payload)
        assert ok is True
        assert "updated" in message.lower()
        assert "BALICE" in node.state["validators"]

        tx1 = build_tx(node, "BALICE", "BBOB", 1.0, 1, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        node.submit_transaction(tx1)
        mined1, _, block1 = node.mine_block("BRESERVE")
        assert mined1 is True
        assert block1["proposer"] == "BRESERVE"

        tx2 = build_tx(node, "BBOB", "BALICE", 1.0, 1, "3f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        node.submit_transaction(tx2)
        mined2, _, block2 = node.mine_block("BALICE")
        assert mined2 is True
        assert block2["proposer"] == "BALICE"


def start_node_server(node):
    server = make_server("127.0.0.1", node.port, create_app(node))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_peer_nodes_sync_longest_valid_chain():
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)

        node_a = BitminiNode(
            node_id="n5a",
            host="127.0.0.1",
            port=9205,
            data_dir=str(Path(temp_dir) / "data-a"),
            genesis_path=str(genesis),
            peer_urls=[],
        )
        node_b = BitminiNode(
            node_id="n5b",
            host="127.0.0.1",
            port=9206,
            data_dir=str(Path(temp_dir) / "data-b"),
            genesis_path=str(genesis),
            peer_urls=[node_a.base_url],
        )
        node_a.peer_urls.add(node_b.base_url)

        server_a, thread_a = start_node_server(node_a)
        try:
            tx = build_tx(node_a, "BALICE", "BBOB", 10.0, 1, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
            node_a.submit_transaction(tx)
            mined, _, block = node_a.mine_block("BRESERVE")
            assert mined is True

            server_b, thread_b = start_node_server(node_b)
            try:
                assert len(node_b.chain) == 1
                synced = node_b.sync_with_peers()
                assert synced is True
                assert len(node_b.chain) == 2
                assert node_b.chain[-1]["hash"] == block["hash"]
                assert node_b.state["accounts"]["BBOB"]["balance"] == 15.0
            finally:
                server_b.shutdown()
                thread_b.join(timeout=5)
        finally:
            server_a.shutdown()
            thread_a.join(timeout=5)


def test_pending_sequential_nonces_from_same_sender_are_accepted():
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)
        node = BitminiNode(
            node_id="n6",
            host="127.0.0.1",
            port=9207,
            data_dir=str(Path(temp_dir) / "data"),
            genesis_path=str(genesis),
            peer_urls=[],
        )

        tx_1 = build_tx(node, "BALICE", "BBOB", 1.0, 1, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        tx_2 = build_tx(node, "BALICE", "BBOB", 2.0, 2, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        tx_3 = build_tx(node, "BALICE", "BBOB", 3.0, 3, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")

        for tx in (tx_1, tx_2, tx_3):
            ok, reason = node.submit_transaction(tx)
            assert ok is True, reason
        assert len(node.mempool) == 3


def test_duplicate_nonce_rejected_before_mining():
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)
        node = BitminiNode(
            node_id="n7",
            host="127.0.0.1",
            port=9208,
            data_dir=str(Path(temp_dir) / "data"),
            genesis_path=str(genesis),
            peer_urls=[],
        )

        tx_1 = build_tx(node, "BALICE", "BBOB", 5.0, 1, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        tx_2 = build_tx(node, "BALICE", "BBOB", 7.0, 1, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        ok_1, message_1 = node.submit_transaction(tx_1)
        assert ok_1 is True
        ok_2, reason_2 = node.submit_transaction(tx_2)
        assert ok_2 is False
        assert "duplicate nonce" in reason_2.lower()


def test_submit_transaction_is_not_blocked_by_peer_broadcast_latency(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)
        node = BitminiNode(
            node_id="n8",
            host="127.0.0.1",
            port=9209,
            data_dir=str(Path(temp_dir) / "data"),
            genesis_path=str(genesis),
            peer_urls=["http://127.0.0.1:9999"],
        )

        def slow_urlopen(req, timeout=1):
            import time
            time.sleep(0.5)
            raise urllib.error.URLError("peer unavailable")

        monkeypatch.setattr("urllib.request.urlopen", slow_urlopen)

        tx = build_tx(node, "BALICE", "BBOB", 2.0, 1, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
        started = time.perf_counter()
        ok, reason = node.submit_transaction(tx)
        elapsed = time.perf_counter() - started
        assert ok is True, reason
        assert elapsed < 0.25, f"submit_transaction blocked on peer broadcast: {elapsed:.3f}s"


def test_mempool_persistence_can_handle_repeated_writes():
    with tempfile.TemporaryDirectory() as temp_dir:
        genesis = Path(temp_dir) / "genesis.json"
        make_genesis(genesis)
        node = BitminiNode(
            node_id="n9",
            host="127.0.0.1",
            port=9210,
            data_dir=str(Path(temp_dir) / "data"),
            genesis_path=str(genesis),
            peer_urls=[],
        )

        for index in range(50):
            payload = {
                "chain_id": node.chain_id,
                "sender": "BALICE",
                "recipient": "BBOB",
                "amount": 0.01 * (index + 1),
                "nonce": index + 1,
                "timestamp": utc_timestamp(),
                "memo": f"persist-{index}",
                "type": "transfer",
            }
            payload["signature"] = node.sign_transaction(payload, "2f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100")
            ok, reason = node.submit_transaction(payload)
            assert ok is True, reason

        for _ in range(20):
            node._persist()

        assert len(node.mempool) >= 1
