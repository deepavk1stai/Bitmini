import sqlite3

import pytest

from app import (
    DB_PATH,
    MAX_SUPPLY,
    app,
    load_state_from_db,
    market_price_for_supply,
    reset_runtime_state,
    save_state_to_db,
    total_supply,
    wallet_state,
    wallets,
)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    reset_runtime_state(persist=True)
    with app.test_client() as client:
        yield client


def register_wallet(client, name, email, username=None, referral_code=None):
    payload = {
        'name': name,
        'username': username or f"@{name.replace(' ', '').lower()}",
        'dateOfBirth': '1995-01-01',
        'zipCode': '10001',
        'email': email,
        'password': 'bitmini123',
    }
    if referral_code:
        payload['referralCode'] = referral_code
    response = client.post('/api/register', json=payload)
    assert response.status_code == 200
    return response.get_json()


def authed_post(client, path, wallet_address, session_token, body=None):
    payload = {'walletAddress': wallet_address}
    if body:
        payload.update(body)
    if path == '/api/send' and 'secret' not in payload:
        payload['securityMethod'] = payload.get('securityMethod', 'password')
        payload['secret'] = 'bitmini123'
    return client.post(path, json=payload, headers={'X-Bitmini-Session': session_token})


def test_wallet_endpoint_returns_zero_balance(client):
    response = client.get('/api/wallet')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['symbol'] == 'BMINI'
    assert payload['balance'] == 1_000_000.0
    assert payload['lockedBalance'] == 1_000_000.0
    assert payload['price'] == 0.0
    assert payload['fiatValue'] == 0.0
    assert payload['network'] == 'Bitmini Testnet'


def test_wallet_app_requires_valid_session(client):
    response = client.get('/app')
    assert response.status_code == 302
    assert 'login_required=1' in response.location


def test_send_allows_session_auth_when_balance_is_available(client):
    wallet_payload = register_wallet(client, 'Secret User', 'secret@example.com', '@secretuser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']
    wallets[wallet_address]['balance'] = 10.0
    wallets[wallet_address]['fiatValue'] = 10.0

    response = client.post(
        '/api/send',
        json={
            'walletAddress': wallet_address,
            'amount': 1.0,
            'recipient': 'B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w',
            'memo': 'Require auth',
        },
        headers={'X-Bitmini-Session': token},
    )
    assert response.status_code == 200
    assert response.get_json()['recipient'] == 'B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w'


def test_market_price_rises_from_user_purchases(client):
    wallet_payload = register_wallet(client, 'Buyer User', 'buyer@example.com', '@buyeruser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    purchase = authed_post(client, '/api/purchase', wallet_address, token, {'usdAmount': 100})
    assert purchase.status_code == 400
    assert 'real money' in purchase.get_json()['error'].lower()

    mine = authed_post(client, '/api/mine', wallet_address, token, {'reward': 10})
    assert mine.status_code == 200

    wallet = client.get(f"/api/wallet?address={wallet_address}").get_json()
    assert wallet['price'] == 0.0
    assert wallet['fiatValue'] == 0.0


def test_market_price_ladder_rises_by_1x_each_10000_tokens(client):
    genesis_wallet = wallets[wallet_state['walletAddress']]
    wallet_state['marketVolumeUsd'] = 1000.0

    genesis_wallet['balance'] = 1_010_000.0
    assert market_price_for_supply() == 0.02

    genesis_wallet['balance'] = 1_020_000.0
    assert market_price_for_supply() == 0.03


def test_sell_and_withdrawal_rails_exist_and_work(client):
    wallet_payload = register_wallet(client, 'Trade User', 'trade@example.com', '@tradeuser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    wallet = wallets[wallet_address]
    wallet['referralActivated'] = True
    wallet['balance'] = 25.0
    wallet_state['price'] = 2.0
    wallet_state['marketVolumeUsd'] = 1000.0
    wallet['fiatValue'] = wallet['balance'] * wallet_state['price']

    sell = authed_post(client, '/api/sell', wallet_address, token, {'tokenAmount': 5.0})
    assert sell.status_code == 200
    assert sell.get_json()['sale']['status'] == 'completed'

    withdraw = authed_post(client, '/api/withdraw', wallet_address, token, {
        'amountUsd': 2.0,
        'method': 'bank',
        'destination': 'Bank ****1234',
    })
    assert withdraw.status_code == 200
    assert withdraw.get_json()['withdrawal']['status'] == 'pending'
    assert withdraw.get_json()['withdrawal']['amountUsd'] == 2.0


def test_purchase_rejects_non_minted_supply(client):
    wallet_payload = register_wallet(client, 'Buy Guard', 'buyguard@example.com', '@buyguard')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    genesis_address = 'B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w'
    wallets[genesis_address]['balance'] = MAX_SUPPLY
    wallets[genesis_address]['lockedBalance'] = MAX_SUPPLY
    wallets[wallet_address]['referralActivated'] = True

    response = authed_post(client, '/api/purchase', wallet_address, token, {'usdAmount': 1})
    assert response.status_code == 400
    assert 'minted' in response.get_json()['error'].lower()
    assert 'non-minted' in response.get_json()['error'].lower()
    assert total_supply() <= MAX_SUPPLY


def test_admin_dashboard_requires_admin_role(client):
    wallet_payload = register_wallet(client, 'Admin User', 'admin@example.com', '@adminuser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    response = client.get('/api/admin', headers={'X-Bitmini-Session': token})
    assert response.status_code == 403
    assert 'admin' in response.get_json()['error'].lower()

    stored_wallet = client.get(f"/api/wallet?address={wallet_address}").get_json()
    assert stored_wallet.get('role') in (None, 'user')


def test_admin_can_approve_a_pending_withdrawal(client):
    user_payload = register_wallet(client, 'Withdrawal User', 'withdrawal@example.com', '@withdrawaluser')
    user_address = user_payload['wallet']['walletAddress']
    user_token = user_payload['sessionToken']

    wallets[user_address]['fiatValue'] = 50.0
    wallets[user_address]['withdrawalRequests'] = [{
        'id': 'WITH-TEST-1',
        'amountUsd': 12.5,
        'method': 'bank',
        'destination': 'Bank ****1234',
        'status': 'pending',
        'createdAt': '2025-01-01T00:00:00Z',
    }]

    admin_payload = register_wallet(client, 'Ops Admin', 'ops@example.com', '@opsadmin')
    admin_address = admin_payload['wallet']['walletAddress']
    admin_token = admin_payload['sessionToken']
    wallets[admin_address]['role'] = 'admin'

    response = authed_post(client, '/api/withdrawal/approve', admin_address, admin_token, {
        'walletAddress': user_address,
        'withdrawalId': 'WITH-TEST-1',
    })

    assert response.status_code == 200
    assert response.get_json()['withdrawal']['status'] == 'approved'
    assert wallets[user_address]['withdrawalRequests'][0]['status'] == 'approved'


def test_admin_can_reject_a_pending_withdrawal(client):
    user_payload = register_wallet(client, 'Rejected User', 'rejected@example.com', '@rejecteduser')
    user_address = user_payload['wallet']['walletAddress']

    wallets[user_address]['fiatValue'] = 50.0
    wallets[user_address]['withdrawalRequests'] = [{
        'id': 'WITH-REJECT-1',
        'amountUsd': 7.5,
        'method': 'bank',
        'destination': 'Bank ****4321',
        'status': 'pending',
        'createdAt': '2025-01-01T00:00:00Z',
    }]

    admin_payload = register_wallet(client, 'Ops Rejector', 'rejector@example.com', '@rejector')
    admin_address = admin_payload['wallet']['walletAddress']
    admin_token = admin_payload['sessionToken']
    wallets[admin_address]['role'] = 'admin'

    response = authed_post(client, '/api/withdrawal/reject', admin_address, admin_token, {
        'walletAddress': user_address,
        'withdrawalId': 'WITH-REJECT-1',
        'reason': 'Manual verification failed',
    })

    assert response.status_code == 200
    assert response.get_json()['withdrawal']['status'] == 'rejected'
    assert wallets[user_address]['withdrawalRequests'][0]['status'] == 'rejected'


def test_network_validator_update_route_requires_admin_and_node_rpc(client):
    wallet_payload = register_wallet(client, 'Node Admin', 'nodeadmin@example.com', '@nodeadmin')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']
    wallets[wallet_address]['role'] = 'admin'

    response = client.post(
        '/api/network/validators/update',
        json={'action': 'add', 'validator': 'BVALID', 'nonce': 1, 'timestamp': '2026-10-04T00:00:00Z'},
        headers={'X-Bitmini-Session': token},
    )

    assert response.status_code == 503
    assert 'node rpc' in response.get_json()['error'].lower()


def test_genesis_locked_balance_is_untouchable(client):
    login = client.post(
        '/api/login',
        json={'walletAddress': 'B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w', 'method': 'password', 'secret': 'genesis123'},
    )
    assert login.status_code == 200
    token = login.get_json()['sessionToken']

    send_attempt = client.post(
        '/api/send',
        json={
            'walletAddress': 'B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w',
            'recipient': 'B9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9Z',
            'amount': 1,
            'memo': 'genesis test',
            'securityMethod': 'password',
            'secret': 'genesis123',
        },
        headers={'X-Bitmini-Session': token},
    )
    assert send_attempt.status_code == 400
    assert 'unlocked' in send_attempt.get_json()['error'].lower()

    stake_attempt = client.post(
        '/api/stake',
        json={'walletAddress': 'B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w', 'amount': 1},
        headers={'X-Bitmini-Session': token},
    )
    assert stake_attempt.status_code == 400
    assert 'unlocked' in stake_attempt.get_json()['error'].lower()


def test_register_requires_identity_fields_and_creates_unique_wallet_id(client):
    missing = client.post('/api/register', json={'name': 'X'})
    assert missing.status_code == 400

    payload = register_wallet(client, 'Nova User', 'nova@example.com', '@novauser')
    assert payload['ok'] is True
    assert payload['wallet']['username'] == '@novauser'
    assert payload['wallet']['walletUniqueId'].startswith('BM-')
    assert payload['wallet'].get('encryptedPrivateKey', '').startswith('enc:v1:')
    assert payload['wallet'].get('encryptedSeedPhrase', '').startswith('enc:v1:')


def test_username_must_be_unique(client):
    register_wallet(client, 'First User', 'first@example.com', '@dupeuser')
    duplicate = client.post(
        '/api/register',
        json={
            'name': 'Second User',
            'username': '@dupeuser',
            'dateOfBirth': '1991-05-05',
            'zipCode': '30301',
            'email': 'second@example.com',
            'password': 'bitmini123',
        },
    )
    assert duplicate.status_code == 409
    assert 'username' in duplicate.get_json()['error'].lower()


def test_login_accepts_username_handle(client):
    wallet_payload = register_wallet(client, 'Login User', 'login@example.com', '@loginuser')
    login = client.post(
        '/api/login',
        json={'username': '@loginuser', 'method': 'password', 'secret': 'bitmini123'},
    )
    assert login.status_code == 200
    assert login.get_json()['wallet']['walletAddress'] == wallet_payload['wallet']['walletAddress']


def test_login_lockout_after_repeated_failed_attempts(client):
    wallet_payload = register_wallet(client, 'Lock User', 'lock@example.com', '@lockuser')
    wallet_address = wallet_payload['wallet']['walletAddress']

    for _ in range(5):
        resp = client.post('/api/login', json={'walletAddress': wallet_address, 'method': 'password', 'secret': 'wrong-pass'})
        assert resp.status_code in (401, 423)

    locked = client.post('/api/login', json={'walletAddress': wallet_address, 'method': 'password', 'secret': 'bitmini123'})
    assert locked.status_code == 423
    assert 'locked' in locked.get_json()['error'].lower()


def test_health_and_admin_audit_endpoints_are_available(client):
    wallet_payload = register_wallet(client, 'Audit User', 'audit@example.com', '@audituser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    health = client.get('/api/health')
    assert health.status_code == 200
    assert health.get_json()['ok'] is True

    wallets[wallet_address]['role'] = 'admin'
    audit = client.get('/api/admin/audit', headers={'X-Bitmini-Session': token})
    assert audit.status_code == 200
    assert audit.get_json()['ok'] is True
    assert 'events' in audit.get_json()


def test_write_endpoints_require_authenticated_session(client):
    wallet_payload = register_wallet(client, 'Auth User', 'auth@example.com', '@authuser')
    wallet_address = wallet_payload['wallet']['walletAddress']

    unauth_send = client.post('/api/send', json={'walletAddress': wallet_address, 'amount': 1, 'recipient': 'B123'})
    assert unauth_send.status_code == 401


def test_authenticated_mine_and_send_flow(client):
    wallet_payload = register_wallet(client, 'Flow User', 'flow@example.com', '@flowuser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    mine = authed_post(client, '/api/mine', wallet_address, token, {'reward': 5})
    assert mine.status_code == 200

    send = authed_post(
        client,
        '/api/send',
        wallet_address,
        token,
        {'amount': 1.25, 'recipient': 'B9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9Z', 'memo': 'test transfer'},
    )
    assert send.status_code == 200

    wallet = client.get(f"/api/wallet?address={wallet_address}").get_json()
    assert wallet['transactions'][0]['type'] == 'Sent'


def test_duplicate_payment_is_rejected(client):
    wallet_payload = register_wallet(client, 'Dup User', 'dup@example.com', '@dupuser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    authed_post(client, '/api/mine', wallet_address, token, {'reward': 10})
    recipient = 'B9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9Z'

    first = authed_post(client, '/api/send', wallet_address, token, {'amount': 2.5, 'recipient': recipient, 'memo': 'same payment'})
    assert first.status_code == 200

    second = authed_post(client, '/api/send', wallet_address, token, {'amount': 2.5, 'recipient': recipient, 'memo': 'same payment'})
    assert second.status_code == 400
    assert 'duplicate' in second.get_json()['error'].lower()


def test_self_send_is_rejected(client):
    wallet_payload = register_wallet(client, 'Self User', 'self@example.com', '@selfuser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    authed_post(client, '/api/mine', wallet_address, token, {'reward': 3})
    self_send = authed_post(client, '/api/send', wallet_address, token, {'amount': 1.0, 'recipient': wallet_address, 'memo': 'self'})
    assert self_send.status_code == 400


def test_wallet_download_requires_auth_and_returns_encrypted_payload(client):
    wallet_payload = register_wallet(client, 'Download User', 'download@example.com', '@dluser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    blocked = client.get(f"/api/wallet/download?address={wallet_address}")
    assert blocked.status_code == 401

    allowed = client.get(f"/api/wallet/download?address={wallet_address}&session={token}")
    assert allowed.status_code == 200
    payload = allowed.get_json()
    assert payload['encryptedPrivateKey'].startswith('enc:v1:')
    assert payload['encryptedSeedPhrase'].startswith('enc:v1:')


def test_purchase_requires_real_money_integration(client):
    wallet_payload = register_wallet(client, 'Real Money User', 'realmoney@example.com', '@realmoneyuser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    purchase = authed_post(client, '/api/purchase', wallet_address, token, {'usdAmount': 100})
    assert purchase.status_code == 400
    assert 'real money' in purchase.get_json()['error'].lower()


def test_sqlite_persistence_reload_keeps_registered_wallet(client):
    wallet_payload = register_wallet(client, 'Persist User', 'persist@example.com', '@persistuser')
    wallet_address = wallet_payload['wallet']['walletAddress']

    reset_runtime_state(persist=False)
    assert load_state_from_db() is True

    wallet_response = client.get('/api/wallet')
    payload = wallet_response.get_json()
    assert payload['walletAddress'] == wallet_address


def test_sqlite_state_is_encrypted_at_rest(client):
    wallet_payload = register_wallet(client, 'Encrypted Store', 'encrypted@example.com', '@encryptedstore')
    wallet_address = wallet_payload['wallet']['walletAddress']

    save_state_to_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute('SELECT key, value FROM state_store').fetchall()

    stored = {key: value for key, value in rows}
    assert 'wallets' in stored
    assert 'walletAddress' not in stored['wallets']
    assert 'email' not in stored['wallets']
    assert wallet_address not in stored['wallets']

    assert 'walletAddress' not in stored['wallet_state']
    assert 'email' not in stored['wallet_state']


def test_token_metrics_endpoint_returns_supply_and_activity_counters(client):
    metrics = client.get('/api/token-metrics')
    assert metrics.status_code == 200
    payload = metrics.get_json()
    assert payload['ok'] is True
    assert payload['supply']['max'] == 21_000_000.0
    assert payload['supply']['lockedGenesisReserve'] == 1_000_000.0
    assert payload['wallets']['total'] >= 1


def test_phase_a_public_testnet_metadata_is_exposed(client):
    response = client.get('/api/network/public')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['ok'] is True
    assert payload['phase'] == 'A'
    assert payload['status'] == 'public-testnet'
    assert payload['network'] == 'Bitmini Testnet'
    assert payload['chainId'] == 'bitmini-testnet-1'
    assert isinstance(payload['seedNodes'], list) and payload['seedNodes']
    assert isinstance(payload['bootstrapPeers'], list) and payload['bootstrapPeers']

    bootstrap = client.get('/api/network/bootstrap')
    assert bootstrap.status_code == 200
    assert bootstrap.get_json()['phase'] == 'B'


def test_phase_b_seed_and_peer_bootstrap_metadata_is_exposed(client):
    response = client.get('/api/network/bootstrap')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['phase'] == 'B'
    assert payload['status'] == 'seed-network-bootstrap'
    assert payload['peerRegistrationEnabled'] is True
    assert isinstance(payload['seedNodes'], list) and payload['seedNodes']
    assert isinstance(payload['bootstrapPeers'], list) and payload['bootstrapPeers']

    registry = client.get('/api/network/peers')
    assert registry.status_code == 200
    registry_payload = registry.get_json()
    assert registry_payload['ok'] is True
    assert isinstance(registry_payload['peers'], list)


def test_referral_signup_bonus_requires_first_transfer_activation(client):
    inviter = register_wallet(client, 'Inviter', 'inviter@example.com', '@inviter')['wallet']
    invitee_payload = register_wallet(client, 'Invitee', 'invitee@example.com', '@invitee', inviter['referralCode'])
    invitee_wallet = invitee_payload['wallet']
    token = invitee_payload['sessionToken']

    invitee_referrals_before = client.get(f"/api/referrals?address={invitee_wallet['walletAddress']}").get_json()
    inviter_referrals_before = client.get(f"/api/referrals?address={inviter['walletAddress']}").get_json()
    assert invitee_referrals_before['pendingActivation'] is True
    assert invitee_referrals_before['lifetimeEarnings'] == 0.0
    assert inviter_referrals_before['lifetimeEarnings'] == 0.0

    authed_post(client, '/api/mine', invitee_wallet['walletAddress'], token, {'reward': 2.0})
    send = authed_post(
        client,
        '/api/send',
        invitee_wallet['walletAddress'],
        token,
        {'amount': 1.0, 'recipient': 'B9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9Z', 'memo': 'activation'},
    )
    assert send.status_code == 200

    invitee_referrals_after = client.get(f"/api/referrals?address={invitee_wallet['walletAddress']}").get_json()
    inviter_referrals_after = client.get(f"/api/referrals?address={inviter['walletAddress']}").get_json()
    assert invitee_referrals_after['pendingActivation'] is False
    assert invitee_referrals_after['lifetimeEarnings'] == 5.0
    assert inviter_referrals_after['lifetimeEarnings'] == 5.0


def test_referral_monthly_cap_limits_purchase_bonus(client):
    inviter = register_wallet(client, 'CapInviter', 'cap-inviter@example.com', '@capinviter')['wallet']
    invitee_payload = register_wallet(client, 'CapInvitee', 'cap-invitee@example.com', '@capinvitee', inviter['referralCode'])
    invitee_wallet = invitee_payload['wallet']
    token = invitee_payload['sessionToken']

    authed_post(client, '/api/mine', invitee_wallet['walletAddress'], token, {'reward': 3.0})
    authed_post(
        client,
        '/api/send',
        invitee_wallet['walletAddress'],
        token,
        {'amount': 1.0, 'recipient': 'B9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9Z', 'memo': 'activate cap'},
    )

    purchase = authed_post(
        client,
        '/api/purchase',
        invitee_wallet['walletAddress'],
        token,
        {'usdAmount': 525000},
    )
    assert purchase.status_code == 200
    purchase_payload = purchase.get_json()
    assert purchase_payload['purchase']['referralBonus'] == 245.0
    assert purchase_payload['purchase']['referrerBonus'] == 245.0
    assert purchase_payload['purchase']['referrerRewardMultiplier'] == 1.0

    invitee_referrals = client.get(f"/api/referrals?address={invitee_wallet['walletAddress']}").get_json()
    inviter_referrals = client.get(f"/api/referrals?address={inviter['walletAddress']}").get_json()
    assert invitee_referrals['monthlyEarnings'] == 250.0
    assert inviter_referrals['monthlyEarnings'] == 250.0
    assert invitee_referrals['monthlyRemaining'] == 0.0


def test_referral_rewards_taper_after_higher_monthly_invite_volume(client):
    inviter = register_wallet(client, 'ScaleInviter', 'scale-inviter@example.com', '@scaleinviter')['wallet']

    def activate_invitee(index):
        invitee_payload = register_wallet(
            client,
            f'ScaleInvitee{index}',
            f'scale-invitee-{index}@example.com',
            f'@scaleinvitee{index}',
            inviter['referralCode'],
        )
        invitee_wallet = invitee_payload['wallet']
        invitee_token = invitee_payload['sessionToken']
        authed_post(client, '/api/mine', invitee_wallet['walletAddress'], invitee_token, {'reward': 2.0})
        send = authed_post(
            client,
            '/api/send',
            invitee_wallet['walletAddress'],
            invitee_token,
            {
                'amount': 1.0,
                'recipient': 'B9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9Z',
                'memo': f'activate {index}',
            },
        )
        assert send.status_code == 200
        return invitee_wallet

    for i in range(1, 4):
        activate_invitee(i)

    fourth_invitee = activate_invitee(4)

    inviter_referrals = client.get(f"/api/referrals?address={inviter['walletAddress']}").get_json()
    fourth_referrals = client.get(f"/api/referrals?address={fourth_invitee['walletAddress']}").get_json()

    assert inviter_referrals['lifetimeEarnings'] == 19.25
    assert inviter_referrals['monthlyRewardEvents'] == 4
    assert inviter_referrals['nextRewardMultiplier'] == 0.85

    assert fourth_referrals['lifetimeEarnings'] == 5.0
    assert fourth_referrals['monthlyRewardEvents'] == 1


def test_leaderboards_and_recent_transactions_api_expose_rankings(client):
    inviter = register_wallet(client, 'Leader Inviter', 'leader-inviter@example.com', '@leaderinviter')['wallet']
    invitee_payload = register_wallet(
        client,
        'Leader Invitee',
        'leader-invitee@example.com',
        '@leaderinvitee',
        inviter['referralCode'],
    )
    invitee_wallet = invitee_payload['wallet']
    invitee_token = invitee_payload['sessionToken']

    authed_post(client, '/api/mine', invitee_wallet['walletAddress'], invitee_token, {'reward': 2.0})
    send = authed_post(
        client,
        '/api/send',
        invitee_wallet['walletAddress'],
        invitee_token,
        {'amount': 1.0, 'recipient': 'B9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9ZZ9Z', 'memo': 'leaderboard activate'},
    )
    assert send.status_code == 200

    leaders = client.get('/api/leaderboards?limit=10')
    assert leaders.status_code == 200
    payload = leaders.get_json()
    assert payload['ok'] is True
    assert 'topReferralEarners' in payload
    assert 'topAdSpenders' in payload
    assert 'daily' in payload['topReferralEarners']
    assert 'weekly' in payload['topReferralEarners']
    assert 'monthly' in payload['topReferralEarners']
    assert isinstance(payload['topContributors'], list)
    assert isinstance(payload['topEarners'], list)
    assert isinstance(payload['topTrade'], list)

    daily = payload['topReferralEarners']['daily']
    assert any(item.get('username') == '@leaderinvitee' for item in daily)

    recent = client.get('/api/transactions/recent?limit=10')
    assert recent.status_code == 200
    recent_payload = recent.get_json()
    assert recent_payload['ok'] is True
    assert len(recent_payload['transactions']) <= 10
    assert all('type' in tx and 'timestamp' in tx for tx in recent_payload['transactions'])


def test_ads_marketplace_priority_and_single_view_enforcement(client):
    seller_payload = register_wallet(client, 'Ad Seller', 'ad-seller@example.com', '@adseller')
    seller_wallet = seller_payload['wallet']
    seller_token = seller_payload['sessionToken']

    set_category = authed_post(
        client,
        '/api/wallet/category',
        seller_wallet['walletAddress'],
        seller_token,
        {'userCategory': 'advertiser'},
    )
    assert set_category.status_code == 200

    viewer_payload = register_wallet(client, 'Ad Viewer', 'ad-viewer@example.com', '@adviewer')
    viewer_wallet = viewer_payload['wallet']
    viewer_token = viewer_payload['sessionToken']

    mine = authed_post(client, '/api/mine', seller_wallet['walletAddress'], seller_token, {'reward': 5.0})
    assert mine.status_code == 200

    ad_a = authed_post(
        client,
        '/api/ads/create',
        seller_wallet['walletAddress'],
        seller_token,
        {
            'adType': 'video',
            'title': 'Video campaign',
            'description': 'High bid video ad',
            'mediaUrl': 'https://example.com/video',
            'bidPerView': 0.02,
            'budgetTotal': 1.0,
        },
    )
    assert ad_a.status_code == 200

    ad_b = authed_post(
        client,
        '/api/ads/create',
        seller_wallet['walletAddress'],
        seller_token,
        {
            'adType': 'site',
            'title': 'Site campaign',
            'description': 'Lower bid site ad',
            'targetUrl': 'https://example.com/site',
            'bidPerView': 0.01,
            'budgetTotal': 1.0,
        },
    )
    assert ad_b.status_code == 200

    market = client.get(
        f"/api/ads/market?address={viewer_wallet['walletAddress']}",
        headers={'X-Bitmini-Session': viewer_token},
    )
    assert market.status_code == 200
    market_payload = market.get_json()
    assert market_payload['ok'] is True
    assert len(market_payload['ads']) >= 2
    assert market_payload['ads'][0]['bidPerView'] >= market_payload['ads'][1]['bidPerView']

    top_ad = market_payload['ads'][0]
    claim_view = authed_post(
        client,
        '/api/ads/view',
        viewer_wallet['walletAddress'],
        viewer_token,
        {'adId': top_ad['id']},
    )
    assert claim_view.status_code == 200
    claim_payload = claim_view.get_json()
    assert claim_payload['ok'] is True
    assert claim_payload['reward'] == top_ad['bidPerView']

    repeat_view = authed_post(
        client,
        '/api/ads/view',
        viewer_wallet['walletAddress'],
        viewer_token,
        {'adId': top_ad['id']},
    )
    assert repeat_view.status_code == 409
    assert 'already viewed' in repeat_view.get_json()['error'].lower()


def test_ad_creation_requires_promoter_or_advertiser_category(client):
    wallet_payload = register_wallet(client, 'Category Check', 'category-check@example.com', '@categorycheck')
    wallet = wallet_payload['wallet']
    token = wallet_payload['sessionToken']

    mine = authed_post(client, '/api/mine', wallet['walletAddress'], token, {'reward': 2.0})
    assert mine.status_code == 200

    denied = authed_post(
        client,
        '/api/ads/create',
        wallet['walletAddress'],
        token,
        {
            'adType': 'site',
            'title': 'Category required ad',
            'targetUrl': 'https://example.com',
            'bidPerView': 0.01,
            'budgetTotal': 0.5,
        },
    )
    assert denied.status_code == 403
    assert 'promoter or advertiser' in denied.get_json()['error'].lower()

    promote = authed_post(
        client,
        '/api/wallet/category',
        wallet['walletAddress'],
        token,
        {'userCategory': 'promoter'},
    )
    assert promote.status_code == 200

    allowed = authed_post(
        client,
        '/api/ads/create',
        wallet['walletAddress'],
        token,
        {
            'adType': 'site',
            'title': 'Promoter ad',
            'targetUrl': 'https://example.com',
            'bidPerView': 0.01,
            'budgetTotal': 0.5,
        },
    )
    assert allowed.status_code == 200


def test_kyc_submission_and_admin_review_flow(client):
    wallet_payload = register_wallet(client, 'KYC User', 'kyc-user@example.com', '@kycuser')
    wallet_address = wallet_payload['wallet']['walletAddress']
    token = wallet_payload['sessionToken']

    submit = client.post(
        '/api/kyc/submit',
        json={
            'walletAddress': wallet_address,
            'country': 'US',
            'documentType': 'passport',
            'riskLevel': 'medium',
        },
        headers={'X-Bitmini-Session': token},
    )
    assert submit.status_code == 200
    assert submit.get_json()['compliance']['kycStatus'] == 'pending'

    compliance = client.get(f'/api/compliance?address={wallet_address}', headers={'X-Bitmini-Session': token})
    assert compliance.status_code == 200
    assert compliance.get_json()['compliance']['kycStatus'] == 'pending'

    admin_payload = register_wallet(client, 'Compliance Admin', 'compliance-admin@example.com', '@complianceadmin')
    admin_address = admin_payload['wallet']['walletAddress']
    admin_token = admin_payload['sessionToken']
    wallets[admin_address]['role'] = 'admin'

    review = client.post(
        '/api/kyc/review',
        json={'walletAddress': wallet_address, 'status': 'approved', 'reviewer': 'ops-admin', 'notes': 'KYC passed'},
        headers={'X-Bitmini-Session': admin_token},
    )
    assert review.status_code == 200
    assert review.get_json()['compliance']['kycStatus'] == 'approved'
    assert review.get_json()['compliance']['amlStatus'] in ('clear', 'pending')


def test_admin_governance_and_launch_readiness_are_exposed(client):
    user_payload = register_wallet(client, 'Governance User', 'governance-user@example.com', '@govuser')
    user_address = user_payload['wallet']['walletAddress']
    user_token = user_payload['sessionToken']

    admin_payload = register_wallet(client, 'Governance Admin', 'governance-admin@example.com', '@govadmin')
    admin_address = admin_payload['wallet']['walletAddress']
    admin_token = admin_payload['sessionToken']
    wallets[admin_address]['role'] = 'admin'

    governance = client.get('/api/admin/governance', headers={'X-Bitmini-Session': admin_token})
    assert governance.status_code == 200
    governance_payload = governance.get_json()
    assert governance_payload['ok'] is True
    assert 'riskControls' in governance_payload
    assert 'launchStatus' in governance_payload
    assert 'checklist' in governance_payload or 'riskControls' in governance_payload

    readiness = client.get('/api/launch/readiness')
    assert readiness.status_code == 200
    readiness_payload = readiness.get_json()
    assert readiness_payload['ok'] is True
    assert isinstance(readiness_payload['checklist'], list)
    assert 'legal' in readiness_payload['status'].lower() or 'blocked' in readiness_payload['status'].lower() or 'ready' in readiness_payload['status'].lower()

    risk_policy = client.post(
        '/api/admin/risk/controls',
        json={'kycRequired': True, 'amlRequired': True, 'sanctionsRequired': True, 'realMoneyDisabled': True},
        headers={'X-Bitmini-Session': admin_token},
    )
    assert risk_policy.status_code == 200
    assert risk_policy.get_json()['riskControls']['kycRequired'] is True

    compliance = client.get(f'/api/compliance?address={user_address}', headers={'X-Bitmini-Session': user_token})
    assert compliance.status_code == 200


def test_database_hardening_snapshot_reports_integrity(client):
    admin_payload = register_wallet(client, 'DB Admin', 'db-admin@example.com', '@dbadmin')
    admin_address = admin_payload['wallet']['walletAddress']
    admin_token = admin_payload['sessionToken']
    wallets[admin_address]['role'] = 'admin'

    response = client.get('/api/admin/db-health', headers={'X-Bitmini-Session': admin_token})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['ok'] is True
    assert 'journalMode' in payload
    assert 'foreignKeys' in payload
    assert 'integrityCheck' in payload
    assert payload['integrityCheck'] in ('ok', 'pass', 'ok-pass')
