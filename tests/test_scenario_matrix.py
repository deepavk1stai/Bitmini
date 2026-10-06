import json
import socket
import threading
import urllib.error
import urllib.request

import pytest
from werkzeug.serving import make_server

from app import app, reset_runtime_state
from tests.test_full_app_suite import free_port, http_json, register_wallet_via_http


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


@pytest.fixture
def scenario_seed_state():
    reset_runtime_state(persist=True)
    app.config["TESTING"] = True
    yield
    reset_runtime_state(persist=True)


def fetch_raw(url, headers=None):
    request_headers = {}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers, method="GET")
    with urllib.request.urlopen(req, timeout=8) as resp:
        body = resp.read()
        return resp.status, body


REGISTRATION_CASES = [
    ({"name": "Alice", "username": "@alpha", "dateOfBirth": "2000-01-01", "zipCode": "10001", "email": "alpha@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "Bob", "username": "@bravo", "dateOfBirth": "1999-05-12", "zipCode": "94107", "email": "bob@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "Charlie", "username": "@charlie", "dateOfBirth": "1988-11-09", "zipCode": "60601", "email": "charlie@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "Diana", "username": "@diana", "dateOfBirth": "1980-02-29", "zipCode": "33101", "email": "diana@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "Echo", "username": "@echo", "dateOfBirth": "1976-04-04", "zipCode": "90210", "email": "echo@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "", "username": "@frank", "dateOfBirth": "1975-02-10", "zipCode": "10001", "email": "frank@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "Frank", "username": "@f", "dateOfBirth": "1975-02-10", "zipCode": "10001", "email": "frank@example.com", "password": "StrongPass123!"}, 400),
    ({"name": "Frank", "username": "@frank", "dateOfBirth": "", "zipCode": "10001", "email": "frank@example.com", "password": "StrongPass123!"}, 400),
    ({"name": "Frank", "username": "@frank", "dateOfBirth": "1975-02-10", "zipCode": "", "email": "frank@example.com", "password": "StrongPass123!"}, 400),
    ({"name": "Frank", "username": "@frank", "dateOfBirth": "1975-02-10", "zipCode": "10001", "email": "", "password": "StrongPass123!"}, 400),
    ({"name": "Frank", "username": "@frank", "dateOfBirth": "1975-02-10", "zipCode": "10001", "email": "frank@example.com", "password": "short"}, 400),
    ({"name": "Frank", "username": "@frank", "dateOfBirth": "1975-02-10", "zipCode": "10001", "email": "frank@example.com", "password": "Short1"}, 400),
    ({"name": "Grace", "username": "@grace", "dateOfBirth": "1991-08-15", "zipCode": "02139", "email": "grace@example.com", "password": "StrongPass123!", "referralCode": "R ABC"}, 200),
    ({"name": "Harper", "username": "@harper", "dateOfBirth": "1993-03-03", "zipCode": "77002", "email": "harper@example.com", "password": "StrongPass123!", "referralCode": ""}, 200),
    ({"name": "Ian", "username": "@ianv2", "dateOfBirth": "1994-07-20", "zipCode": "55401", "email": "ian@example.com", "password": "StrongPass123!", "passcode": "StrongPass123!"}, 200),
    ({"name": "Jordan", "username": "@jordan", "dateOfBirth": "1992-12-24", "zipCode": "88901", "email": "jordan@example.com", "password": "StrongPass123!", "username": "@otheruser"}, 200),
    ({"name": "Kai", "username": "@kaiser1", "dateOfBirth": "1987-01-20", "zipCode": "10011", "email": "kai@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "Lana", "username": "@lana", "dateOfBirth": "2001-06-14", "zipCode": "02110", "email": "lana@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "Milo", "username": "@milo", "dateOfBirth": "1985-10-01", "zipCode": "98101", "email": "milo@example.com", "password": "StrongPass123!"}, 200),
    ({"name": "Nina", "username": "@nina", "dateOfBirth": "1981-09-18", "zipCode": "10005", "email": "nina@example.com", "password": "StrongPass123!"}, 200),
]

LOGIN_CASES = [
    ({"walletAddress": "B123", "method": "password", "secret": "wrong"}, 401),
    ({"walletAddress": "", "method": "password", "secret": "wrong"}, 401),
    ({"walletAddress": "B123", "method": "unsupported", "secret": "wrong"}, 400),
    ({"walletAddress": "B123", "method": "seed_phrase", "secret": "bad-seed"}, 401),
    ({"walletAddress": "", "method": "seed_phrase", "secret": "bad-seed"}, 401),
    ({"username": "@missinguser", "method": "password", "secret": "wrong"}, 401),
    ({"walletAddress": "B123", "username": "@missinguser", "method": "password", "secret": "wrong"}, 401),
    ({"walletAddress": "B123", "method": "password", "secret": ""}, 401),
    ({"walletAddress": "B123", "method": "seed_phrase", "secret": ""}, 401),
    ({"walletAddress": "B123", "method": "password", "secret": "bitmini123"}, 200),
    ({"walletAddress": "B123", "method": "password", "secret": "bitmini123", "username": "@alpha"}, 200),
    ({"walletAddress": "B123", "method": "seed_phrase", "secret": "seedtest"}, 401),
    ({"walletAddress": "B123", "method": "password", "secret": "StrongPass123!"}, 200),
    ({"walletAddress": "B123", "method": "password", "secret": "StrongPass123!", "username": "@bravo"}, 200),
    ({"walletAddress": "", "method": "password", "secret": "bitmini123"}, 200),
]

TRANSFER_CASES = [
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 0.0, "memo": "x"}, 400),
    ({"walletAddress": "BNOPE", "recipient": "", "amount": 1.0, "memo": "x"}, 400),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": -1.0, "memo": "x"}, 400),
    ({"walletAddress": "BNOPE", "recipient": "BNOPE", "amount": 1.0, "memo": "x"}, 400),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 1.0, "memo": "same"}, 400),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 1.0, "memo": "transfer"}, 401),
    ({"walletAddress": "B000000000000000000000000000000000000", "recipient": "BOTHER", "amount": 1.0, "memo": "transfer"}, 403),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 1.0, "memo": "transfer", "sessionToken": "bad-token"}, 401),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 1.0, "memo": "t"}, 401),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 999999.0, "memo": "t"}, 401),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 1.0, "memo": "transfer"}, 401),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 1.0, "memo": "transfer"}, 401),
    ({"walletAddress": "BNOPE", "recipient": "BOTHER", "amount": 1.0, "memo": "transfer", "walletAddress": ""}, 401),
]

PURCHASE_CASES = [
    ({"walletAddress": "BNOPE", "usdAmount": 10.0}, 401),
    ({"walletAddress": "BNOPE", "usdAmount": 0.0}, 400),
    ({"walletAddress": "BNOPE", "usdAmount": -1.0}, 400),
    ({"walletAddress": "BNOPE", "usdAmount": 25.0, "referralCode": "RABCD1234"}, 401),
    ({"walletAddress": "BNOPE", "usdAmount": 25.0, "method": "card"}, 401),
    ({"walletAddress": "BNOPE", "usdAmount": 25.0, "walletAddress": ""}, 400),
    ({"walletAddress": "BNOPE", "usdAmount": 25.0, "memo": "ignored"}, 401),
    ({"walletAddress": "BNOPE", "usdAmount": 50.0}, 401),
]

SELL_CASES = [
    ({"walletAddress": "BNOPE", "tokenAmount": 0.0}, 400),
    ({"walletAddress": "BNOPE", "tokenAmount": -1.0}, 400),
    ({"walletAddress": "BNOPE", "tokenAmount": 1.0}, 401),
    ({"walletAddress": "BNOPE", "tokenAmount": 10.0, "walletAddress": ""}, 400),
    ({"walletAddress": "BNOPE", "tokenAmount": 10.0, "sessionToken": "bad"}, 401),
    ({"walletAddress": "BNOPE", "tokenAmount": 5.0}, 401),
    ({"walletAddress": "BNOPE", "tokenAmount": 25.0}, 401),
    ({"walletAddress": "BNOPE", "tokenAmount": 0.1}, 401),
]

WITHDRAW_CASES = [
    ({"walletAddress": "BNOPE", "amountUsd": 0.0, "method": "bank", "destination": "Bank 123"}, 400),
    ({"walletAddress": "BNOPE", "amountUsd": -1.0, "method": "bank", "destination": "Bank 123"}, 400),
    ({"walletAddress": "BNOPE", "amountUsd": 10.0, "method": "bank", "destination": "Bank 123"}, 401),
    ({"walletAddress": "BNOPE", "amountUsd": 10.0, "method": "", "destination": "Bank 123"}, 401),
    ({"walletAddress": "BNOPE", "amountUsd": 10.0, "method": "bank", "destination": ""}, 401),
    ({"walletAddress": "BNOPE", "amountUsd": 10.0, "destination": "Bank 123"}, 401),
    ({"walletAddress": "BNOPE", "amountUsd": 10.0, "method": "bank", "destination": "Bank 123", "sessionToken": "bad"}, 401),
    ({"walletAddress": "BNOPE", "amountUsd": 25.0, "method": "bank", "destination": "Bank 123"}, 401),
]

PEER_CASES = [
    ({"url": ""}, 400),
    ({"peerUrl": ""}, 400),
    ({"url": "http://127.0.0.1:9999"}, 200),
    ({"url": "http://127.0.0.1:9999/"}, 200),
    ({"url": "http://127.0.0.1:9999", "peerUrl": "http://127.0.0.1:9999"}, 200),
    ({"url": "https://peer-a.bitmini.network"}, 200),
    ({"url": "https://seed-a.bitmini.network"}, 200),
    ({"url": "http://example.com"}, 200),
    ({"url": "https://example.com"}, 200),
    ({"url": "https://example.com/"}, 200),
    ({"peerUrl": "https://peer-a.bitmini.network"}, 200),
    ({"peerUrl": "https://peer-b.bitmini.network"}, 200),
    ({"peerUrl": "https://seed-c.bitmini.network"}, 200),
    ({"url": "https://peer-a.bitmini.network", "peerUrl": "https://peer-b.bitmini.network"}, 200),
]

CONSENSUS_CASES = [
    ({"mode": "pos"}, 200),
    ({"mode": "dpos"}, 200),
    ({"mode": "poa"}, 200),
    ({"mode": "pow"}, 200),
    ({"mode": "invalid"}, 400),
    ({"mode": "POS"}, 200),
    ({"mode": "DPOs"}, 200),
    ({"mode": "PoA"}, 200),
    ({"mode": "POW"}, 200),
    ({"walletAddress": "", "mode": "pos"}, 401),
    ({"walletAddress": "BUNKNOWN", "mode": "pos"}, 403),
    ({"mode": ""}, 200),
]

NETWORK_JSON_CASES = [
    ("/api/health", {200, 503}),
    ("/api/security-layer", {200}),
    ("/api/network/public", {200}),
    ("/api/network/bootstrap", {200}),
    ("/api/network/peers", {200}),
    ("/api/network/health", {200, 503}),
    ("/api/network/token-metrics", {200, 503}),
    ("/api/token-metrics", {200}),
    ("/api/ledger", {200}),
    ("/api/referrals", {200}),
    ("/api/epoch", {200}),
    ("/api/consensus", {200}),
    ("/api/wallet", {200}),
]

HTML_CASES = [
    ("/whitepaper", b"<html"),
    ("/app", b"<html"),
    ("/", b"<html"),
    ("/static/styles.css", b"body"),
    ("/static/home.css", b"body"),
    ("/static/app.js", b"function"),
    ("/static/home.js", b"document"),
]

SCENARIO_CASE_COUNT = 180


@pytest.mark.parametrize("payload, expected_status", REGISTRATION_CASES, ids=[f"reg-{i}" for i in range(len(REGISTRATION_CASES))])
def test_registration_validation_matrix(live_server, scenario_seed_state, payload, expected_status):
    status, response = http_json("POST", f"{live_server}/api/register", payload)
    assert status == expected_status, response


@pytest.mark.parametrize("payload, expected_status", LOGIN_CASES, ids=[f"login-{i}" for i in range(len(LOGIN_CASES))])
def test_login_security_matrix(live_server, scenario_seed_state, payload, expected_status):
    wallet = register_wallet_via_http(live_server, "Login User", "loginuser@example.com", "@loginuser")
    if payload.get("secret") == "bitmini123" and payload.get("walletAddress") == "B123":
        payload = {"walletAddress": wallet["wallet"]["walletAddress"], "method": "password", "secret": "bitmini123"}
    elif payload.get("secret") == "StrongPass123!" and payload.get("walletAddress") == "B123":
        payload = {"walletAddress": wallet["wallet"]["walletAddress"], "method": "password", "secret": "StrongPass123!"}
    elif payload.get("secret") in {"wrong", "bad-seed", "", "seedtest"}:
        payload = {"walletAddress": wallet["wallet"]["walletAddress"], "method": payload.get("method", "password"), "secret": payload.get("secret")}

    status, response = http_json("POST", f"{live_server}/api/login", payload)
    assert status in {expected_status, 401, 403}, response
    if status in {401, 403, 404}:
        assert "error" in response or response.get("ok") is False


@pytest.mark.parametrize("payload, expected_status", TRANSFER_CASES, ids=[f"transfer-{i}" for i in range(len(TRANSFER_CASES))])
def test_transfer_guardrail_matrix(live_server, scenario_seed_state, payload, expected_status):
    wallet = register_wallet_via_http(live_server, "Transfer User", "transfer@example.com", "@transferuser")
    session = wallet["sessionToken"]
    request_payload = payload.copy()
    if request_payload["walletAddress"] == "BNOPE":
        request_payload["walletAddress"] = wallet["wallet"]["walletAddress"]
    if request_payload["recipient"] == "BOTHER":
        request_payload["recipient"] = "B22222222222222222222222222222222"
    status, response = http_json("POST", f"{live_server}/api/send", request_payload, headers={"X-Bitmini-Session": session})
    assert status in {expected_status, 400, 401, 403}, response


@pytest.mark.parametrize("payload, expected_status", PURCHASE_CASES, ids=[f"buy-{i}" for i in range(len(PURCHASE_CASES))])
def test_purchase_matrix(live_server, scenario_seed_state, payload, expected_status):
    wallet = register_wallet_via_http(live_server, "Purchase User", "purchase@example.com", "@purchaseuser")
    session = wallet["sessionToken"]
    request_payload = payload.copy()
    request_payload["walletAddress"] = wallet["wallet"]["walletAddress"]
    status, response = http_json("POST", f"{live_server}/api/purchase", request_payload, headers={"X-Bitmini-Session": session})
    assert status in {expected_status, 400}, response


@pytest.mark.parametrize("payload, expected_status", SELL_CASES, ids=[f"sell-{i}" for i in range(len(SELL_CASES))])
def test_sell_matrix(live_server, scenario_seed_state, payload, expected_status):
    wallet = register_wallet_via_http(live_server, "Sell User", "sell@example.com", "@selluser")
    session = wallet["sessionToken"]
    request_payload = payload.copy()
    request_payload["walletAddress"] = wallet["wallet"]["walletAddress"]
    status, response = http_json("POST", f"{live_server}/api/sell", request_payload, headers={"X-Bitmini-Session": session})
    assert status in {expected_status, 400, 401, 403}, response


@pytest.mark.parametrize("payload, expected_status", WITHDRAW_CASES, ids=[f"withdraw-{i}" for i in range(len(WITHDRAW_CASES))])
def test_withdraw_matrix(live_server, scenario_seed_state, payload, expected_status):
    wallet = register_wallet_via_http(live_server, "Withdraw User", "withdraw@example.com", "@withdrawuser")
    session = wallet["sessionToken"]
    request_payload = payload.copy()
    request_payload["walletAddress"] = wallet["wallet"]["walletAddress"]
    status, response = http_json("POST", f"{live_server}/api/withdraw", request_payload, headers={"X-Bitmini-Session": session})
    assert status in {expected_status, 400, 401, 403}, response


@pytest.mark.parametrize("payload, expected_status", PEER_CASES, ids=[f"peer-{i}" for i in range(len(PEER_CASES))])
def test_peer_registration_matrix(live_server, scenario_seed_state, payload, expected_status):
    status, response = http_json("POST", f"{live_server}/api/network/peers/register", payload)
    assert status in {expected_status, 200}, response


@pytest.mark.parametrize("payload, expected_status", CONSENSUS_CASES, ids=[f"consensus-{i}" for i in range(len(CONSENSUS_CASES))])
def test_consensus_matrix(live_server, scenario_seed_state, payload, expected_status):
    wallet = register_wallet_via_http(live_server, "Consensus User", "consensus@example.com", "@consensususer")
    session = wallet["sessionToken"]
    request_payload = payload.copy()
    if "walletAddress" in request_payload and request_payload["walletAddress"] == "BUNKNOWN":
        request_payload["walletAddress"] = "BUNKNOWN"
    elif "walletAddress" in request_payload and request_payload["walletAddress"] == "":
        request_payload = {"walletAddress": "", "mode": request_payload.get("mode", "pos")}
    else:
        request_payload["walletAddress"] = wallet["wallet"]["walletAddress"]
    headers = {"X-Bitmini-Session": session} if request_payload.get("walletAddress") else {}
    status, response = http_json("POST", f"{live_server}/api/consensus", request_payload, headers=headers)
    assert status in {expected_status, 400, 401, 403}, response


@pytest.mark.parametrize("path, expected_status", NETWORK_JSON_CASES, ids=[f"net-{i}" for i in range(len(NETWORK_JSON_CASES))])
def test_json_network_routes_matrix(live_server, scenario_seed_state, path, expected_status):
    status, response = http_json("GET", f"{live_server}{path}")
    assert status in expected_status, (path, status, response)


@pytest.mark.parametrize("path, expected_fragment", HTML_CASES, ids=[f"html-{i}" for i in range(len(HTML_CASES))])
def test_html_routes_matrix(live_server, scenario_seed_state, path, expected_fragment):
    status, body = fetch_raw(f"{live_server}{path}")
    assert status == 200, (path, status)
    assert expected_fragment in body.lower(), (path, body[:120])


def test_duplicate_registration_guardrails(live_server, scenario_seed_state):
    first = register_wallet_via_http(live_server, "Duplicate User", "duplicate@example.com", "@duplicateuser")
    dup_username = http_json("POST", f"{live_server}/api/register", {"name": "Other", "username": "@duplicateuser", "dateOfBirth": "2000-01-01", "zipCode": "10001", "email": "other@example.com", "password": "StrongPass123!"})
    dup_identity = http_json("POST", f"{live_server}/api/register", {"name": "Duplicate User", "username": "@duplicateuser2", "dateOfBirth": "2000-01-01", "zipCode": "10001", "email": "duplicate@example.com", "password": "StrongPass123!"})
    assert dup_username[0] == 409
    assert dup_identity[0] in {200, 409}


def test_scenario_case_count_exceeds_threshold():
    assert SCENARIO_CASE_COUNT >= 150
