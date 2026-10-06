import json
import socket
import threading
import urllib.error
import urllib.request

import pytest
from werkzeug.serving import make_server

from app import app, reset_runtime_state, total_supply, wallets


@pytest.fixture
def isolated_app_state():
    reset_runtime_state(persist=True)
    app.config["TESTING"] = True
    yield
    reset_runtime_state(persist=True)


@pytest.fixture
def live_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    server = make_server("127.0.0.1", port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{port}"

    try:
        server.shutdown()
    except Exception:
        pass
    try:
        server.server_close()
    except Exception:
        pass
    thread.join(timeout=5)


def http_json(method, url, payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") or "{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"raw": body}
        return exc.code, data


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_test_server(port):
    server = make_server("127.0.0.1", port, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def register_wallet_via_http(base_url, name, email, username):
    status, payload = http_json(
        "POST",
        f"{base_url}/api/register",
        {
            "name": name,
            "username": username,
            "dateOfBirth": "1996-02-15",
            "zipCode": "75001",
            "email": email,
            "password": "bitmini123",
        },
    )
    assert status == 200, payload
    return payload


def login_via_http(base_url, wallet_address, password):
    status, payload = http_json(
        "POST",
        f"{base_url}/api/login",
        {"walletAddress": wallet_address, "method": "password", "secret": password},
    )
    assert status == 200, payload
    return payload


def test_end_to_end_positive_wallet_flow_and_real_transactions(isolated_app_state, live_server):
    base_url = live_server
    buyer = register_wallet_via_http(base_url, "Alpha Buyer", "alpha@example.com", "@alphabuyer")
    seller = register_wallet_via_http(base_url, "Bravo Seller", "bravo@example.com", "@bravoseller")

    buyer_wallet = buyer["wallet"]
    seller_wallet = seller["wallet"]
    buyer_session = buyer["sessionToken"]
    seller_session = seller["sessionToken"]

    status, wallet_payload = http_json(
        "GET",
        f"{base_url}/api/wallet?address={buyer_wallet['walletAddress']}",
        headers={"X-Bitmini-Session": buyer_session},
    )
    assert status == 200
    assert wallet_payload["walletAddress"] == buyer_wallet["walletAddress"]
    assert buyer_wallet["balance"] == 0.0
    assert wallet_payload["balance"] == 0.0

    status, mined = http_json(
        "POST",
        f"{base_url}/api/mine",
        {"walletAddress": buyer_wallet["walletAddress"], "reward": 5.0},
        headers={"X-Bitmini-Session": buyer_session},
    )
    assert status == 200, mined
    assert mined["reward"] > 0

    status, rejected_self = http_json(
        "POST",
        f"{base_url}/api/send",
        {"walletAddress": buyer_wallet["walletAddress"], "recipient": buyer_wallet["walletAddress"], "amount": 1.0, "memo": "self transfer"},
        headers={"X-Bitmini-Session": buyer_session},
    )
    assert status == 400
    assert "same wallet" in rejected_self["error"].lower()

    status, transfer = http_json(
        "POST",
        f"{base_url}/api/send",
        {"walletAddress": buyer_wallet["walletAddress"], "recipient": seller_wallet["walletAddress"], "amount": 2.0, "memo": "payment"},
        headers={"X-Bitmini-Session": buyer_session},
    )
    assert status == 200, transfer
    assert transfer["recipient"] == seller_wallet["walletAddress"]

    status, duplicate = http_json(
        "POST",
        f"{base_url}/api/send",
        {"walletAddress": buyer_wallet["walletAddress"], "recipient": seller_wallet["walletAddress"], "amount": 2.0, "memo": "payment"},
        headers={"X-Bitmini-Session": buyer_session},
    )
    assert status == 400
    assert "duplicate" in duplicate["error"].lower()

    wallets[seller_wallet["walletAddress"]]["fiatValue"] = 10.0
    wallets[seller_wallet["walletAddress"]]["balance"] = 10.0

    status, withdraw = http_json(
        "POST",
        f"{base_url}/api/withdraw",
        {"walletAddress": seller_wallet["walletAddress"], "amountUsd": 1.0, "method": "bank", "destination": "Bank 1234"},
        headers={"X-Bitmini-Session": seller_session},
    )
    assert status == 200, withdraw
    withdrawal_id = withdraw["withdrawal"]["id"]

    admin_wallet = register_wallet_via_http(base_url, "Ops Admin", "ops@example.com", "@opsadmin")
    admin_session = admin_wallet["sessionToken"]
    admin_address = admin_wallet["wallet"]["walletAddress"]
    wallets[admin_address]["role"] = "admin"

    status, approved = http_json(
        "POST",
        f"{base_url}/api/withdrawal/approve",
        {"walletAddress": seller_wallet["walletAddress"], "withdrawalId": withdrawal_id},
        headers={"X-Bitmini-Session": admin_session},
    )
    assert status == 200
    assert approved["withdrawal"]["status"] == "approved"

    status, metrics = http_json("GET", f"{base_url}/api/token-metrics")
    assert status == 200
    assert metrics["supply"]["max"] == 21000000.0
    assert total_supply() <= 21000000.0


def test_negative_wallet_security_and_admin_guardrails(isolated_app_state, live_server):
    base_url = live_server

    bad = http_json("POST", f"{base_url}/api/register", {"name": "X"})
    assert bad[0] == 400

    first = register_wallet_via_http(base_url, "Ranger One", "ranger1@example.com", "@rangerone")
    second = http_json(
        "POST",
        f"{base_url}/api/register",
        {
            "name": "Ranger One",
            "username": "@rangerone",
            "dateOfBirth": "1990-01-01",
            "zipCode": "10001",
            "email": "ranger2@example.com",
            "password": "bitmini123",
        },
    )
    assert second[0] == 409
    assert "already" in second[1]["error"].lower() or "use" in second[1]["error"].lower()

    invalid = http_json(
        "POST",
        f"{base_url}/api/login",
        {"walletAddress": first["wallet"]["walletAddress"], "method": "password", "secret": "wrong-password"},
    )
    assert invalid[0] == 401
    assert "invalid" in invalid[1]["error"].lower()

    user_wallet = first["wallet"]
    session = first["sessionToken"]
    status, forbidden = http_json("GET", f"{base_url}/api/admin", headers={"X-Bitmini-Session": session})
    assert status == 403
    assert "admin" in forbidden["error"].lower()

    status, real_money = http_json(
        "POST",
        f"{base_url}/api/purchase",
        {"walletAddress": user_wallet["walletAddress"], "usdAmount": 10.0},
        headers={"X-Bitmini-Session": session},
    )
    assert status == 400
    assert "real money" in real_money["error"].lower() or "minted" in real_money["error"].lower()

    status, balance_error = http_json(
        "POST",
        f"{base_url}/api/send",
        {"walletAddress": user_wallet["walletAddress"], "recipient": "B9X1234567890ABCDEF1234567890XYZ", "amount": 999999.0, "memo": "overspend"},
        headers={"X-Bitmini-Session": session},
    )
    assert status == 400
    assert "insufficient" in balance_error["error"].lower() or "unlocked" in balance_error["error"].lower()


def test_multiple_node_instances_register_peers_and_report_health(isolated_app_state):
    ports = [free_port() for _ in range(3)]
    servers = []
    try:
        for port in ports:
            server, thread = start_test_server(port)
            servers.append((server, thread, port))

        base_urls = [f"http://127.0.0.1:{port}" for _, _, port in servers]

        for base_url in base_urls:
            status, payload = http_json("GET", f"{base_url}/api/health")
            assert status == 200
            assert payload["status"] == "ok"
            assert payload["network"] == "Bitmini Testnet"

        status, peer_register = http_json(
            "POST",
            f"{base_urls[0]}/api/network/peers/register",
            {"url": f"http://127.0.0.1:{ports[1]}"},
        )
        assert status == 200
        assert peer_register["ok"] is True
        assert f"http://127.0.0.1:{ports[1]}" in peer_register["peers"]

        status, peer_second = http_json(
            "POST",
            f"{base_urls[1]}/api/network/peers/register",
            {"url": f"http://127.0.0.1:{ports[2]}"},
        )
        assert status == 200
        assert f"http://127.0.0.1:{ports[2]}" in peer_second["peers"]

        status, peers = http_json("GET", f"{base_urls[0]}/api/network/peers")
        assert status == 200
        assert peers["phase"] == "B"
        assert isinstance(peers["peers"], list)
        assert len(peers["peers"]) >= 2

        status, invalid_peer = http_json("POST", f"{base_urls[0]}/api/network/peers/register", {"url": ""})
        assert status == 400
        assert "required" in invalid_peer["error"].lower()
    finally:
        for server, thread, _ in servers:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
            thread.join(timeout=5)


def test_peer_registration_deduplicates_and_rejects_missing_url(isolated_app_state):
    ports = [free_port() for _ in range(2)]
    servers = []
    try:
        for port in ports:
            server, thread = start_test_server(port)
            servers.append((server, thread, port))

        base_urls = [f"http://127.0.0.1:{port}" for _, _, port in servers]
        peer_url = f"http://127.0.0.1:{ports[1]}"

        status, empty = http_json("POST", f"{base_urls[0]}/api/network/peers/register", {"url": ""})
        assert status == 400
        assert "required" in empty["error"].lower()

        status, first = http_json("POST", f"{base_urls[0]}/api/network/peers/register", {"url": peer_url})
        assert status == 200
        assert peer_url in first["peers"]

        status, second = http_json("POST", f"{base_urls[0]}/api/network/peers/register", {"url": peer_url})
        assert status == 200
        assert first["peers"] == second["peers"]
        assert first["peers"].count(peer_url) == 1
    finally:
        for server, thread, _ in servers:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
            thread.join(timeout=5)


def test_peer_registry_propagates_across_three_nodes(isolated_app_state):
    ports = [free_port() for _ in range(3)]
    servers = []
    try:
        for port in ports:
            server, thread = start_test_server(port)
            servers.append((server, thread, port))

        base_urls = [f"http://127.0.0.1:{port}" for _, _, port in servers]
        for index in range(1, len(base_urls)):
            status, payload = http_json(
                "POST",
                f"{base_urls[0]}/api/network/peers/register",
                {"url": base_urls[index]},
            )
            assert status == 200, payload
            assert base_urls[index] in payload["peers"]

        status, peers = http_json("GET", f"{base_urls[0]}/api/network/peers")
        assert status == 200
        assert peers["ok"] is True
        assert isinstance(peers["peers"], list)
        for candidate in base_urls[1:]:
            assert candidate in peers["peers"]

        for base_url in base_urls[1:]:
            status, peer_snapshot = http_json("GET", f"{base_url}/api/network/peers")
            assert status == 200
            assert peers["peers"] == peer_snapshot["peers"] or len(peer_snapshot["peers"]) >= 2
    finally:
        for server, thread, _ in servers:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
            thread.join(timeout=5)


def test_persistence_and_network_metadata_are_consistent(isolated_app_state, live_server):
    base_url = live_server
    wallet = register_wallet_via_http(base_url, "Persist User", "persist@example.com", "@persistuser")
    address = wallet["wallet"]["walletAddress"]
    session_token = wallet["sessionToken"]

    status, public_net = http_json("GET", f"{base_url}/api/network/public")
    assert status == 200
    assert public_net["phase"] == "A"
    assert public_net["status"] == "public-testnet"

    status, bootstrap = http_json("GET", f"{base_url}/api/network/bootstrap")
    assert status == 200
    assert bootstrap["phase"] == "B"
    assert bootstrap["status"] == "seed-network-bootstrap"

    status, health = http_json("GET", f"{base_url}/api/health")
    assert status == 200
    assert health["status"] == "ok"

    status, wallet_again = http_json("GET", f"{base_url}/api/wallet?address={address}", headers={"X-Bitmini-Session": session_token})
    assert status == 200
    assert wallet_again["walletAddress"] == address
    assert wallet_again["username"] == "@persistuser"
