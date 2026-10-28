import json

from app import app, current_epoch_seconds, reset_runtime_state, wallets


def test_devnet_status_and_launch_routes_are_available():
    reset_runtime_state(persist=True)
    app.config["TESTING"] = True

    status = app.test_client().get("/api/network/devnet")
    assert status.status_code == 200
    payload = status.get_json()
    assert payload["ok"] is True
    assert payload["devnet"]["validatorCount"] >= 4
    assert payload["status"] == "prototype"

    admin_wallet = app.test_client().post(
        "/api/register",
        json={
            "name": "Ops Devnet",
            "username": "@opsdevnet",
            "dateOfBirth": "1990-01-01",
            "zipCode": "10001",
            "email": "opsdevnet@example.com",
            "password": "bitmini123",
        },
    )
    assert admin_wallet.status_code == 200
    admin_session = admin_wallet.get_json()["sessionToken"]
    admin_address = admin_wallet.get_json()["wallet"]["walletAddress"]
    wallets[admin_address]["role"] = "admin"

    launch = app.test_client().post(
        "/api/network/devnet/start",
        json={"count": 4, "basePort": 9101, "autoMine": True, "duration": 8, "dryRun": True},
        headers={"X-Bitmini-Session": admin_session},
    )
    assert launch.status_code == 200
    route_payload = launch.get_json()
    assert route_payload["ok"] is True
    assert route_payload["count"] == 4
    assert "command" in route_payload

    stop = app.test_client().post(
        "/api/network/devnet/stop",
        json={},
        headers={"X-Bitmini-Session": admin_session},
    )
    assert stop.status_code == 200
    assert stop.get_json()["ok"] is True

    reset_runtime_state(persist=True)


def test_unstake_route_releases_staked_balance():
    reset_runtime_state(persist=True)
    app.config["TESTING"] = True

    wallet_address = "BTESTUNSTAKE0000000000000000"
    wallets[wallet_address] = {
        "name": "Stake Tester",
        "username": "@teststake",
        "role": "user",
        "walletAddress": wallet_address,
        "balance": 100.0,
        "stakedBalance": 25.0,
        "lockedBalance": 0.0,
        "fiatValue": 0.0,
        "sessions": [{"token": "stake-token", "expiresAt": current_epoch_seconds() + 3600}],
        "transactions": [],
        "referralMonthly": {},
        "userCategory": "validator",
        "userCategories": ["validator"],
        "auditLog": [],
        "lastActiveAt": "2026-01-01T00:00:00Z",
        "status": "Verified",
    }

    unstake = app.test_client().post(
        "/api/stake/unstake",
        json={"amount": 10.0, "walletAddress": wallet_address},
        headers={"X-Bitmini-Session": "stake-token"},
    )
    assert unstake.status_code == 200
    payload = unstake.get_json()
    assert payload["ok"] is True
    assert payload["wallet"]["balance"] == 110.0
    assert payload["wallet"]["stakedBalance"] == 15.0

    reset_runtime_state(persist=True)
