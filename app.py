import base64
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import qrcode
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from flask import Flask, Response, jsonify, redirect, render_template, request, url_for

def runtime_secret_key():
    configured = os.environ.get("BITMINI_DB_KEY") or os.environ.get("BITMINI_SECRET_KEY")
    if configured:
        return configured.strip()

    key_path = os.environ.get(
        "BITMINI_DB_KEY_PATH",
        os.path.join(os.path.expanduser("~"), ".bitmini", "db.key"),
    )
    os.makedirs(os.path.dirname(key_path), exist_ok=True)

    if os.path.exists(key_path):
        with open(key_path, "r", encoding="utf-8") as handle:
            stored_key = handle.read().strip()
            if stored_key:
                return stored_key

    generated_key = secrets.token_hex(32)
    with open(key_path, "w", encoding="utf-8") as handle:
        handle.write(generated_key)
    return generated_key


app = Flask(__name__)
app.config["SECRET_KEY"] = runtime_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("BITMINI_ENV", "development").lower() == "production"
app.config["JSON_SORT_KEYS"] = False

MAX_SUPPLY = 21_000_000.0
GENESIS_UNTOUCHABLE_SUPPLY = 1_000_000.0
COIN_DECIMALS = 9
BASE_NETWORK_PRICE = 0.0
DEFAULT_CONSENSUS_MODE = "pos"
DEFAULT_PHASE = "B"
DEFAULT_TESTNET_STATUS = "seed-network-bootstrap"
DEFAULT_CHAIN_ID = "bitmini-testnet-1"
DEFAULT_SEED_NODES = [
    "https://seed-a.bitmini.network",
    "https://seed-b.bitmini.network",
    "https://seed-c.bitmini.network",
]
DEFAULT_BOOTSTRAP_PEERS = [
    "https://peer-a.bitmini.network",
    "https://peer-b.bitmini.network",
    "https://peer-c.bitmini.network",
]
NETWORK_PEER_STATE = {
    "seedNodes": list(DEFAULT_SEED_NODES),
    "bootstrapPeers": list(DEFAULT_BOOTSTRAP_PEERS),
    "peers": list(dict.fromkeys([*DEFAULT_BOOTSTRAP_PEERS, *DEFAULT_SEED_NODES])),
}
EPOCH_LENGTH = 3
DB_PATH = os.environ.get("BITMINI_DB_PATH", os.path.join(os.path.dirname(__file__), "bitmini.db"))
NODE_RPC_URL = os.environ.get("BITMINI_NODE_RPC_URL", "").strip().rstrip("/")
SLASH_RATE = 0.1
MIN_SLASH = 1.0
REFERRAL_SIGNUP_BONUS = 5.0
REFERRAL_PURCHASE_BONUS_RATE = 0.02
REFERRAL_MONTHLY_CAP = 250.0
REFERRAL_REWARD_TIERS = [
    (3, 1.0),
    (10, 0.85),
    (25, 0.65),
    (float("inf"), 0.4),
]
AD_ALLOWED_TYPES = {"video", "site", "poster"}
USER_CATEGORIES = {"consumer", "validator", "promoter", "advertiser"}
AD_SELLER_CATEGORIES = {"promoter", "advertiser"}
AD_MIN_BID_PER_VIEW = 0.000001
AD_MAX_BID_PER_VIEW = 250.0
AD_MIN_BUDGET = 0.0001
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 15 * 60
AUDIT_LOG_LIMIT = 50
REWARD_HALVING_INTERVAL_DAYS = 365 * 4
CAPACITY_EXPANSION_INTERVAL_DAYS = 183
CAPACITY_WALLET_STEP = 250_000.0
CAPACITY_TIME_STEP = 500_000.0
CONSENSUS_PROFILES = {
    "pow": {
        "label": "Proof of Work",
        "mobile_ready": False,
        "energy": "High",
        "stake_required": 0.0,
        "default_reward": 10.0,
        "stake_bonus_rate": 0.0,
    },
    "pos": {
        "label": "Proof of Stake",
        "mobile_ready": True,
        "energy": "Low",
        "stake_required": 25.0,
        "default_reward": 2.0,
        "stake_bonus_rate": 0.04,
    },
    "dpos": {
        "label": "Delegated Proof of Stake",
        "mobile_ready": True,
        "energy": "Very low",
        "stake_required": 10.0,
        "default_reward": 1.5,
        "stake_bonus_rate": 0.03,
    },
    "poa": {
        "label": "Proof of Authority",
        "mobile_ready": True,
        "energy": "Very low",
        "stake_required": 0.0,
        "default_reward": 1.0,
        "stake_bonus_rate": 0.0,
    },
}


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def network_start_datetime():
    return datetime(2024, 1, 1, tzinfo=timezone.utc)


def reward_halving_epoch():
    delta_seconds = max((datetime.now(timezone.utc) - network_start_datetime()).total_seconds(), 0.0)
    return int(delta_seconds // (REWARD_HALVING_INTERVAL_DAYS * 24 * 60 * 60))


def effective_reward_for_mode(mode, requested_reward=None):
    profile, normalized = consensus_profile(mode)
    base_reward = float(requested_reward) if requested_reward is not None else float(profile["default_reward"])
    halving_epoch = reward_halving_epoch()
    if halving_epoch > 0:
        base_reward = max(base_reward / (2 ** halving_epoch), 0.0001)
    return round(base_reward, 4), normalized, profile


def current_network_capacity():
    wallet_count = max(len(wallets), 1)
    delta_seconds = max((datetime.now(timezone.utc) - network_start_datetime()).total_seconds(), 0.0)
    expansion_cycles = int(delta_seconds // (CAPACITY_EXPANSION_INTERVAL_DAYS * 24 * 60 * 60))
    wallet_growth_bonus = max(wallet_count - 1, 0) * CAPACITY_WALLET_STEP
    time_growth_bonus = expansion_cycles * CAPACITY_TIME_STEP
    return round(MAX_SUPPLY + wallet_growth_bonus + time_growth_bonus, 4)


def market_price_for_supply():
    circulating = max(total_supply(), GENESIS_UNTOUCHABLE_SUPPLY)
    minted_after_genesis = max(circulating - GENESIS_UNTOUCHABLE_SUPPLY, 0.0)
    level_index = int(minted_after_genesis // 10_000.0)
    level_floor = round(0.01 * (1 + level_index), 4)
    market_volume = float(wallet_state.get("marketVolumeUsd", 0.0))
    if market_volume <= 0:
        return 0.0
    demand_price = market_volume / circulating
    return round(max(level_floor, demand_price), 4)


def parse_utc_timestamp(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_bootstrap_list(raw_value):
    if raw_value is None:
        return []

    values = []
    for item in re.split(r"[,;\n]+", str(raw_value).strip()):
        candidate = item.strip().strip("\"'")
        if candidate:
            values.append(candidate)
    return values


def ranked_wallet_identity(wallet_address):
    wallet, resolved = get_wallet(wallet_address)
    if wallet:
        return {
            "walletAddress": resolved,
            "username": wallet.get("username") or "",
            "name": wallet.get("name") or "Unknown",
        }
    return {
        "walletAddress": str(wallet_address or "").strip(),
        "username": "",
        "name": "Unknown",
    }


def parse_tx_numeric_value(tx):
    raw = str(tx.get("value", "0") or "0").replace(",", "").strip()
    if raw.startswith("+"):
        raw = raw[1:]
    try:
        return float(raw)
    except ValueError:
        return 0.0


def recent_ledger_transactions(limit=10):
    entries = []
    max_items = max(int(limit or 10), 1)
    for block in reversed(ledger.get("blocks", [])):
        block_index = block.get("index")
        block_timestamp = block.get("timestamp")
        for tx in reversed(block.get("transactions", [])):
            recipient = tx.get("recipient", "")
            identity = ranked_wallet_identity(recipient)
            entries.append(
                {
                    "blockIndex": block_index,
                    "timestamp": block_timestamp,
                    "type": tx.get("type"),
                    "value": tx.get("value"),
                    "amount": tx.get("amount"),
                    "note": tx.get("note"),
                    "memo": tx.get("memo"),
                    "positive": bool(tx.get("positive")),
                    "walletAddress": identity.get("walletAddress"),
                    "username": identity.get("username"),
                    "name": identity.get("name"),
                    "counterparty": recipient,
                }
            )
            if len(entries) >= max_items:
                return entries
    return entries


def top_referral_earners_since(period_delta, limit=10):
    cutoff = datetime.now(timezone.utc) - period_delta
    totals = {}
    for block in reversed(ledger.get("blocks", [])):
        block_dt = parse_utc_timestamp(block.get("timestamp"))
        if block_dt and block_dt < cutoff:
            continue
        for tx in block.get("transactions", []):
            if tx.get("type") != "Referral":
                continue
            recipient = str(tx.get("recipient") or "").strip()
            if not recipient:
                continue
            value = max(parse_tx_numeric_value(tx), 0.0)
            if value <= 0:
                continue
            totals[recipient] = totals.get(recipient, 0.0) + value

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[: max(int(limit or 10), 1)]
    payload = []
    for wallet_address, value in ranked:
        identity = ranked_wallet_identity(wallet_address)
        payload.append(
            {
                "walletAddress": identity["walletAddress"],
                "username": identity["username"],
                "name": identity["name"],
                "referralEarnings": round(value, 4),
            }
        )
    return payload


def top_wallet_metric(metric_key, limit=10):
    values = []
    for wallet in wallets.values():
        address = str(wallet.get("walletAddress") or "").strip()
        if not address:
            continue

        metric = 0.0
        txs = wallet.get("transactions", [])
        if metric_key == "contributors":
            for tx in txs:
                if tx.get("type") in {"Validated", "Mined"}:
                    metric += max(parse_tx_numeric_value(tx), 0.0)
        elif metric_key == "earners":
            metric = float(wallet.get("referralEarnings", 0.0))
            for tx in txs:
                if tx.get("type") in {"Validated", "Mined"}:
                    metric += max(parse_tx_numeric_value(tx), 0.0)
        elif metric_key == "trade":
            for tx in txs:
                if tx.get("type") in {"Bought", "Sold"}:
                    metric += abs(parse_tx_numeric_value(tx))

        if metric <= 0:
            continue
        values.append((address, metric))

    ranked = sorted(values, key=lambda item: item[1], reverse=True)[: max(int(limit or 10), 1)]
    result = []
    for wallet_address, metric in ranked:
        identity = ranked_wallet_identity(wallet_address)
        result.append(
            {
                "walletAddress": identity["walletAddress"],
                "username": identity["username"],
                "name": identity["name"],
                "score": round(metric, 4),
            }
        )
    return result


def ads_store():
    market = wallet_state.setdefault("adsMarketplace", {})
    ads = market.setdefault("ads", [])
    if not isinstance(ads, list):
        market["ads"] = []
        ads = market["ads"]
    return ads


def normalize_ad_type(value):
    return str(value or "").strip().lower()


def normalize_external_link(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    return f"https://{raw}"


def ad_viewers(ad):
    viewers = ad.setdefault("viewers", [])
    if isinstance(viewers, list):
        return viewers
    ad["viewers"] = list(viewers) if viewers else []
    return ad["viewers"]


def ad_budget_remaining(ad):
    return round(float(ad.get("budgetRemaining", 0.0)), COIN_DECIMALS)


def ad_is_active_for_view(ad):
    status = str(ad.get("status", "active")).strip().lower()
    bid = float(ad.get("bidPerView", 0.0))
    return status == "active" and bid > 0 and ad_budget_remaining(ad) >= bid


def ad_payload_for_viewer(ad, viewer_address=None):
    seller_identity = ranked_wallet_identity(ad.get("sellerWalletAddress"))
    seller_wallet, _ = get_wallet(ad.get("sellerWalletAddress"))
    seller_category = normalize_user_category((seller_wallet or {}).get("userCategory", "consumer"))
    viewers = set(ad_viewers(ad))
    has_viewed = bool(viewer_address and viewer_address in viewers)
    remaining = ad_budget_remaining(ad)
    return {
        "id": ad.get("id"),
        "title": ad.get("title"),
        "description": ad.get("description"),
        "adType": ad.get("adType"),
        "mediaUrl": ad.get("mediaUrl"),
        "targetUrl": ad.get("targetUrl"),
        "sellerWalletAddress": ad.get("sellerWalletAddress"),
        "sellerUsername": seller_identity.get("username"),
        "sellerName": seller_identity.get("name"),
        "sellerCategory": seller_category,
        "bidPerView": float(ad.get("bidPerView", 0.0)),
        "budgetTotal": float(ad.get("budgetTotal", 0.0)),
        "budgetRemaining": remaining,
        "viewCount": int(ad.get("viewCount", 0)),
        "status": ad.get("status", "active"),
        "createdAt": ad.get("createdAt"),
        "hasViewed": has_viewed,
        "eligibleToView": ad_is_active_for_view(ad) and not has_viewed,
    }


def ranked_ads_for_viewer(viewer_address=None):
    ordered = sorted(
        ads_store(),
        key=lambda ad: (
            -float(ad.get("bidPerView", 0.0)),
            float(ad.get("budgetRemaining", 0.0)) <= 0,
            str(ad.get("createdAt", "")),
        ),
    )
    return [ad_payload_for_viewer(ad, viewer_address=viewer_address) for ad in ordered]


def make_ad_transaction(wallet, amount, tx_type, note, memo, positive):
    sign = "+" if positive else "-"
    tx = {
        "type": tx_type,
        "value": f"{sign}{float(amount):.{COIN_DECIMALS}f}",
        "amount": f"{sign}${(wallet_state['price'] * float(amount)):,.2f}",
        "note": note,
        "time": "Now",
        "positive": bool(positive),
        "recipient": wallet.get("walletAddress"),
        "memo": memo,
    }
    wallet.setdefault("transactions", [])
    wallet["transactions"].insert(0, tx)
    wallet["fiatValue"] = float(wallet.get("balance", 0.0)) * float(wallet_state.get("price", 0.0))
    touch_wallet_activity(wallet)
    sync_active_wallet(wallet)
    return tx


def top_ad_spenders(limit=10):
    best_bid = {}
    for ad in ads_store():
        seller = str(ad.get("sellerWalletAddress") or "").strip()
        if not seller:
            continue
        bid = float(ad.get("bidPerView", 0.0))
        current = best_bid.get(seller, 0.0)
        if bid > current:
            best_bid[seller] = bid

    ranked = sorted(best_bid.items(), key=lambda item: item[1], reverse=True)[: max(int(limit or 10), 1)]
    payload = []
    for wallet_address, bid in ranked:
        identity = ranked_wallet_identity(wallet_address)
        payload.append(
            {
                "walletAddress": identity["walletAddress"],
                "username": identity["username"],
                "name": identity["name"],
                "maxBidPerView": round(float(bid), COIN_DECIMALS),
            }
        )
    return payload


def phase_a_public_testnet_config():
    seed_nodes = parse_bootstrap_list(os.environ.get("BITMINI_SEED_NODES")) or list(NETWORK_PEER_STATE["seedNodes"])
    bootstrap_peers = parse_bootstrap_list(os.environ.get("BITMINI_BOOTSTRAP_PEERS")) or list(NETWORK_PEER_STATE["bootstrapPeers"])
    all_peers = list(dict.fromkeys([*bootstrap_peers, *seed_nodes, *NETWORK_PEER_STATE["peers"]]))
    NETWORK_PEER_STATE["seedNodes"] = seed_nodes
    NETWORK_PEER_STATE["bootstrapPeers"] = bootstrap_peers
    NETWORK_PEER_STATE["peers"] = all_peers
    chain_id = str(os.environ.get("BITMINI_CHAIN_ID", DEFAULT_CHAIN_ID)).strip() or DEFAULT_CHAIN_ID
    return {
        "ok": True,
        "phase": "A",
        "status": "public-testnet",
        "network": wallet_state.get("network", "Bitmini Testnet"),
        "chainId": chain_id,
        "seedNodes": seed_nodes,
        "bootstrapPeers": bootstrap_peers,
        "peers": all_peers,
        "peerRegistrationEnabled": False,
        "walletUrl": "/app",
        "publicApi": "/api/network/public",
        "launchNote": "Phase A is the public testnet bootstrap with wallet distribution and seed discovery.",
    }


def phase_b_bootstrap_config():
    public_state = phase_a_public_testnet_config()
    public_state.update(
        {
            "phase": DEFAULT_PHASE,
            "status": DEFAULT_TESTNET_STATUS,
            "peerRegistrationEnabled": True,
            "launchNote": "Phase B focuses on public seed-node discovery, peer registration, and the first open testnet bootstrap cycle.",
        }
    )
    public_state["peers"] = list(dict.fromkeys(NETWORK_PEER_STATE["peers"]))
    public_state["bootstrapPeers"] = list(dict.fromkeys(NETWORK_PEER_STATE["bootstrapPeers"]))
    public_state["seedNodes"] = list(dict.fromkeys(NETWORK_PEER_STATE["seedNodes"]))
    return public_state


def node_rpc_enabled():
    return bool(NODE_RPC_URL)


def node_rpc_request(method, path, payload=None, timeout=3):
    if not node_rpc_enabled():
        return 503, {"ok": False, "error": "Node RPC is not configured."}

    url = f"{NODE_RPC_URL}{path}"
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content = response.read().decode("utf-8") or "{}"
            return response.status, json.loads(content)
    except urllib.error.HTTPError as exc:
        content = exc.read().decode("utf-8") or "{}"
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = {"ok": False, "error": content}
        return exc.code, payload
    except Exception as exc:
        return 502, {"ok": False, "error": f"Node RPC unreachable: {exc}"}


def ed25519_generate_private_hex():
    private = ed25519.Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_bytes.hex()


def ed25519_public_hex_from_private(private_hex):
    private = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    public_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return public_bytes.hex()


def ed25519_sign_payload(private_hex, payload):
    private = ed25519.Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    return private.sign(payload.encode("utf-8")).hex()


def current_month_key():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def touch_wallet_activity(wallet):
    wallet["lastActiveAt"] = utc_timestamp()


def record_wallet_audit_event(wallet, event_type, message, details=None, severity="info"):
    if not wallet:
        return
    details = details or {}
    entry = {
        "timestamp": utc_timestamp(),
        "type": str(event_type or "event").strip() or "event",
        "severity": str(severity or "info").strip() or "info",
        "message": str(message or "Wallet event").strip() or "Wallet event",
        "details": details,
    }
    audit_log = list(wallet.get("auditLog") or [])
    audit_log.insert(0, entry)
    wallet["auditLog"] = audit_log[:AUDIT_LOG_LIMIT]
    wallet["lastAuditAt"] = entry["timestamp"]


def wallet_login_lock_status(wallet):
    if not wallet:
        return False, 0
    lock_until = int(wallet.get("loginLockedUntil", 0) or 0)
    if lock_until > current_epoch_seconds():
        return True, max(lock_until - current_epoch_seconds(), 1)
    if lock_until > 0:
        wallet["failedLoginAttempts"] = 0
        wallet["loginLockedUntil"] = 0
    return False, 0


def monthly_referral_earned(wallet, month_key=None):
    key = month_key or current_month_key()
    monthly = wallet.get("referralMonthly", {})
    return float(monthly.get(key, 0.0))


def referral_cap_remaining(wallet, month_key=None):
    earned = monthly_referral_earned(wallet, month_key=month_key)
    return max(REFERRAL_MONTHLY_CAP - earned, 0.0)


def record_referral_earning(wallet, amount, month_key=None):
    key = month_key or current_month_key()
    monthly = wallet.setdefault("referralMonthly", {})
    monthly[key] = round(float(monthly.get(key, 0.0)) + float(amount), 4)


def monthly_referral_reward_count(wallet, month_key=None):
    key = month_key or current_month_key()
    monthly_counts = wallet.get("referralRewardCountMonthly", {})
    try:
        return int(monthly_counts.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def record_referral_reward_count(wallet, increment=1, month_key=None):
    key = month_key or current_month_key()
    monthly_counts = wallet.setdefault("referralRewardCountMonthly", {})
    current = monthly_referral_reward_count(wallet, month_key=key)
    monthly_counts[key] = max(current + int(increment), 0)


def referral_reward_multiplier_for_wallet(wallet, month_key=None):
    payout_index = monthly_referral_reward_count(wallet, month_key=month_key) + 1
    for max_count, multiplier in REFERRAL_REWARD_TIERS:
        if payout_index <= max_count:
            return float(multiplier)
    return float(REFERRAL_REWARD_TIERS[-1][1])


def preview_referral_bonus(wallet, referrer_wallet, amount, month_key=None):
    month = month_key or current_month_key()
    base_amount = max(float(amount), 0.0)
    buyer_allowed = min(base_amount, referral_cap_remaining(wallet, month_key=month))
    referrer_allowed = min(base_amount, referral_cap_remaining(referrer_wallet, month_key=month))
    referrer_multiplier = referral_reward_multiplier_for_wallet(referrer_wallet, month_key=month)
    buyer_bonus = round(buyer_allowed, 4)
    referrer_bonus = round(referrer_allowed * referrer_multiplier, 4)
    return buyer_bonus, referrer_bonus, referrer_multiplier


def apply_referral_bonus(wallet, referrer_wallet, amount, buyer_memo, referrer_memo, note):
    if amount <= 0:
        return 0.0, 0.0, 0.0

    month = current_month_key()
    buyer_bonus, referrer_bonus, referrer_multiplier = preview_referral_bonus(
        wallet=wallet,
        referrer_wallet=referrer_wallet,
        amount=amount,
        month_key=month,
    )
    mint_total = round(buyer_bonus + referrer_bonus, 4)
    if mint_total <= 0:
        return 0.0, 0.0, referrer_multiplier

    if not can_mint(mint_total):
        return 0.0, 0.0, referrer_multiplier

    if buyer_bonus > 0:
        credit_wallet(
            wallet=wallet,
            wallet_address=wallet["walletAddress"],
            amount=buyer_bonus,
            tx_type="Referral",
            note=note,
            memo=buyer_memo,
        )
        wallet["referralEarnings"] = round(float(wallet.get("referralEarnings", 0.0)) + buyer_bonus, 4)
        record_referral_earning(wallet, buyer_bonus, month_key=month)
        record_referral_reward_count(wallet, month_key=month)

    if referrer_bonus > 0:
        credit_wallet(
            wallet=referrer_wallet,
            wallet_address=referrer_wallet["walletAddress"],
            amount=referrer_bonus,
            tx_type="Referral",
            note=note,
            memo=referrer_memo,
        )
        referrer_wallet["referralEarnings"] = round(float(referrer_wallet.get("referralEarnings", 0.0)) + referrer_bonus, 4)
        record_referral_earning(referrer_wallet, referrer_bonus, month_key=month)
        record_referral_reward_count(referrer_wallet, month_key=month)

    return buyer_bonus, referrer_bonus, referrer_multiplier


def activate_referral_on_first_transfer(wallet):
    if not wallet.get("referredBy"):
        return 0.0
    if wallet.get("referralActivated"):
        return 0.0

    referrer_wallet, _ = get_wallet(wallet.get("referredBy"))
    if not referrer_wallet:
        return 0.0

    granted, _, _ = apply_referral_bonus(
        wallet=wallet,
        referrer_wallet=referrer_wallet,
        amount=REFERRAL_SIGNUP_BONUS,
        buyer_memo="Referral activated by first transfer",
        referrer_memo=f"Friend activated: {wallet.get('walletAddress')}",
        note="Referral activation bonus",
    )
    if granted > 0:
        wallet["referralActivated"] = True
    return granted


def hash_block(block):
    block_payload = json.dumps(block, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(block_payload).hexdigest()


def generate_wallet_address():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "B" + "".join(secrets.choice(alphabet) for _ in range(28))


def generate_referral_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "R" + "".join(secrets.choice(alphabet) for _ in range(8))


def generate_wallet_unique_id(name, date_of_birth, zip_code, email):
    identity = f"{name.strip().lower()}|{date_of_birth.strip()}|{zip_code.strip()}|{email.strip().lower()}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20].upper()
    return f"BM-{digest}"


def normalize_username(username):
    raw = str(username or "").strip().lower()
    raw = raw.lstrip("@").rstrip("@")
    if not raw:
        return ""
    if not re.fullmatch(r"[a-z0-9._-]{3,24}", raw):
        return ""
    return f"@{raw}"


def normalize_user_category(value):
    normalized = str(value or "").strip().lower()
    if normalized in USER_CATEGORIES:
        return normalized
    return "consumer"


def current_epoch_seconds():
    return int(datetime.now(timezone.utc).timestamp())


def hash_passcode(passcode, salt):
    digest = hashlib.pbkdf2_hmac("sha256", passcode.encode("utf-8"), salt.encode("utf-8"), 120000)
    return digest.hex()


def hash_seed_phrase(seed_phrase):
    return hashlib.sha256(seed_phrase.encode("utf-8")).hexdigest()


def _derive_secret_key(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200000, dklen=32)


def _keystream_bytes(key, nonce, length):
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])


def encrypt_secret(plaintext, password, salt):
    plain_bytes = str(plaintext or "").encode("utf-8")
    key = _derive_secret_key(password, salt)
    nonce = secrets.token_bytes(16)
    stream = _keystream_bytes(key, nonce, len(plain_bytes))
    cipher_bytes = bytes(a ^ b for a, b in zip(plain_bytes, stream))
    return "enc:v1:" + base64.urlsafe_b64encode(nonce + cipher_bytes).decode("utf-8")


def decrypt_secret(ciphertext, password, salt):
    data = str(ciphertext or "")
    if not data:
        return ""
    if not data.startswith("enc:v1:"):
        return data

    raw = base64.urlsafe_b64decode(data.split("enc:v1:", 1)[1].encode("utf-8"))
    nonce = raw[:16]
    cipher_bytes = raw[16:]
    key = _derive_secret_key(password, salt)
    stream = _keystream_bytes(key, nonce, len(cipher_bytes))
    plain_bytes = bytes(a ^ b for a, b in zip(cipher_bytes, stream))
    return plain_bytes.decode("utf-8")


def create_wallet_session(wallet, network_private_key=None):
    token = secrets.token_urlsafe(32)
    session = {
        "token": token,
        "createdAt": utc_timestamp(),
        "expiresAt": current_epoch_seconds() + SESSION_TTL_SECONDS,
        "level": "passcode+session",
    }
    if network_private_key:
        session["networkPrivateKey"] = network_private_key
    wallet.setdefault("sessions", [])
    wallet["sessions"] = wallet["sessions"][-4:] + [session]
    return session


def get_active_session_for_token(wallet, session_token):
    token = str(session_token or "").strip()
    if not token:
        return None
    now = current_epoch_seconds()
    for session in wallet.get("sessions", []):
        if session.get("token") == token and int(session.get("expiresAt", 0)) > now:
            return session
    return None


def get_wallet_from_session(session_token):
    token = str(session_token or "").strip()
    if not token:
        return None

    now = current_epoch_seconds()
    for wallet in wallets.values():
        active_sessions = []
        for session in wallet.get("sessions", []):
            if int(session.get("expiresAt", 0)) > now:
                active_sessions.append(session)
            if session.get("token") == token and int(session.get("expiresAt", 0)) > now:
                wallet["sessions"] = active_sessions
                return wallet
        wallet["sessions"] = active_sessions
    return None


def authorize_wallet_request(payload=None):
    data = payload or {}
    requested_address = str(data.get("walletAddress", "") or "").strip()
    session_token = request.headers.get("X-Bitmini-Session") or str(data.get("sessionToken", "") or "").strip()
    wallet = get_wallet_from_session(session_token)
    if not wallet:
        return None, None, (jsonify({"ok": False, "error": "Authentication required. Please login first."}), 401)

    session_wallet_address = wallet.get("walletAddress")
    if requested_address and requested_address != session_wallet_address:
        return None, None, (jsonify({"ok": False, "error": "Unauthorized wallet access attempt blocked."}), 403)

    return wallet, session_wallet_address, None


def wallet_has_admin_role(wallet):
    if not wallet:
        return False
    return str(wallet.get("role", "user")).strip().lower() == "admin"


def authorize_admin_request(payload=None):
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return None, None, auth_error
    if not wallet_has_admin_role(wallet):
        return None, None, (jsonify({"ok": False, "error": "Admin access is restricted. This wallet does not have the admin role."}), 403)
    return wallet, wallet_address, None


def consensus_profile(mode):
    normalized = str(mode or DEFAULT_CONSENSUS_MODE).strip().lower()
    return CONSENSUS_PROFILES.get(normalized, CONSENSUS_PROFILES[DEFAULT_CONSENSUS_MODE]), normalized


def default_wallet_state():
    return {
        "name": "Bitmini Wallet",
        "symbol": "BMINI",
        "balance": GENESIS_UNTOUCHABLE_SUPPLY,
        "lockedBalance": GENESIS_UNTOUCHABLE_SUPPLY,
        "price": BASE_NETWORK_PRICE,
        "fiatValue": 0.0,
        "marketVolumeUsd": 0.0,
        "walletAddress": "B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w",
        "mode": "Genesis block",
        "userCategory": "validator",
        "userCategories": ["validator", "promoter"],
        "consensusMode": DEFAULT_CONSENSUS_MODE,
        "consensusLabel": CONSENSUS_PROFILES[DEFAULT_CONSENSUS_MODE]["label"],
        "stakedBalance": 0.0,
        "slashedTotal": 0.0,
        "saleHistory": [],
        "withdrawalRequests": [],
        "status": "Verified",
        "network": "Bitmini Testnet",
        "transactions": [
            {
                "type": "Genesis",
                "value": f"+{GENESIS_UNTOUCHABLE_SUPPLY:.4f}",
                "amount": "+$0.00",
                "note": "Genesis reserve minted (untouchable)",
                "time": "Just now",
                "positive": True,
                "recipient": "B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w",
                "memo": "1M untouchable genesis reserve",
            }
        ],
        "alerts": [
            {"label": "Price alert: $34,000", "status": "Activated", "value": "+3.2%"},
            {"label": "10% movement alert", "status": "Watching", "value": "+2.1%"},
            {"label": "Portfolio value target", "status": "Ready", "value": "+6.5%"},
        ],
        "contacts": [
            {"name": "Aster Labs", "address": "B8N9...9d4f", "tag": "Trusted"},
            {"name": "Smith Holdings", "address": "B12A...e2cd", "tag": "Business"},
            {"name": "Luna Pay", "address": "B4c0...11ae", "tag": "Merchant"},
        ],
        "adsMarketplace": {
            "ads": [],
        },
    }


def default_validator_state():
    return {
        "epoch": 1,
        "epochLength": EPOCH_LENGTH,
        "validatedCount": 0,
        "slashEvents": 0,
        "selected": {},
    }


wallet_state = default_wallet_state()
wallets = {}
ledger = {"blocks": []}
validator_state = default_validator_state()


def db_encryption_key():
    raw_key = runtime_secret_key()
    if not raw_key:
        raise RuntimeError("A runtime database encryption key is required for Bitmini state persistence.")
    return base64.urlsafe_b64encode(hashlib.sha256(str(raw_key).encode("utf-8")).digest())


def encrypt_persisted_value(payload):
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return Fernet(db_encryption_key()).encrypt(serialized).decode("utf-8")


def decrypt_persisted_value(raw_value):
    if raw_value is None:
        return {}
    value_text = str(raw_value)
    if not value_text:
        return {}
    try:
        decrypted = Fernet(db_encryption_key()).decrypt(value_text.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except InvalidToken:
        if value_text.lstrip().startswith("{") or value_text.lstrip().startswith("["):
            return json.loads(value_text)
        raise


def init_storage():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_state_to_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO state_store(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("wallet_state", encrypt_persisted_value(wallet_state)),
        )
        conn.execute(
            "INSERT INTO state_store(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("wallets", encrypt_persisted_value(wallets)),
        )
        conn.execute(
            "INSERT INTO state_store(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("ledger", encrypt_persisted_value(ledger)),
        )
        conn.execute(
            "INSERT INTO state_store(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("validator_state", encrypt_persisted_value(validator_state)),
        )
        conn.commit()


def load_state_from_db():
    global wallet_state, wallets, ledger, validator_state
    if not os.path.exists(DB_PATH):
        return False

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT key, value FROM state_store").fetchall()

    state_map = {key: value for key, value in rows}
    required_keys = {"wallet_state", "wallets", "ledger", "validator_state"}
    if not required_keys.issubset(state_map.keys()):
        return False

    wallet_state.clear()
    wallet_state.update(decrypt_persisted_value(state_map["wallet_state"]))
    wallets.clear()
    wallets.update(decrypt_persisted_value(state_map["wallets"]))
    ledger.clear()
    ledger.update(decrypt_persisted_value(state_map["ledger"]))
    validator_state.clear()
    validator_state.update(decrypt_persisted_value(state_map["validator_state"]))

    return True


def wallet_download_payload(wallet):
    return {
        "name": wallet.get("name", "Bitmini Wallet"),
        "username": wallet.get("username"),
        "email": wallet.get("email"),
        "dateOfBirth": wallet.get("dateOfBirth"),
        "zipCode": wallet.get("zipCode"),
        "walletAddress": wallet["walletAddress"],
        "walletUniqueId": wallet.get("walletUniqueId"),
        "networkPublicKey": wallet.get("networkPublicKey"),
        "encryptedPrivateKey": wallet.get("encryptedPrivateKey"),
        "encryptedSeedPhrase": wallet.get("encryptedSeedPhrase"),
        "encryption": {
            "algorithm": "PBKDF2-SHA256 + SHA256-CTR-XOR",
            "version": "enc:v1",
        },
        "balance": float(wallet.get("balance", 0.0)),
        "symbol": wallet.get("symbol", "BMINI"),
        "network": wallet.get("network", "Bitmini Testnet"),
        "securityMethods": wallet.get("securityMethods", ["password", "seed_phrase", "session_token"]),
        "referralCode": wallet.get("referralCode"),
        "referredBy": wallet.get("referredBy"),
        "referralEarnings": float(wallet.get("referralEarnings", 0.0)),
        "consensusMode": wallet.get("consensusMode", DEFAULT_CONSENSUS_MODE),
        "stakedBalance": float(wallet.get("stakedBalance", 0.0)),
        "slashedTotal": float(wallet.get("slashedTotal", 0.0)),
        "createdAt": wallet.get("createdAt", utc_timestamp()),
    }


def wallet_public_payload(wallet):
    payload = dict(wallet)
    for key in [
        "privateKey",
        "seedPhrase",
        "encryptedPrivateKey",
        "encryptedSeedPhrase",
        "seedPhraseHash",
        "authSalt",
        "passcodeHash",
        "sessions",
    ]:
        payload.pop(key, None)
    return payload


def round_coin(value):
    return round(float(value), COIN_DECIMALS)


def total_supply():
    wallet_total = sum(
        float(wallet.get("balance", 0.0)) + float(wallet.get("stakedBalance", 0.0))
        for wallet in wallets.values()
    )
    if wallet_total <= 0.0:
        return round_coin(float(wallet_state.get("balance", 0.0)) + float(wallet_state.get("stakedBalance", 0.0)))
    return round_coin(wallet_total)


def can_mint(amount):
    return total_supply() + float(amount) <= MAX_SUPPLY


def issuance_mode_status():
    if total_supply() >= MAX_SUPPLY:
        return {
            "status": "fee_or_stake",
            "reason": "All BMINI coins have been minted. Rewards are now fee- and stake-based.",
            "remaining": 0.0,
            "max_supply": MAX_SUPPLY,
        }
    return {
        "status": "minting",
        "reason": "Issuance is still active and decays every four years until the network reaches full minting.",
        "remaining": max(MAX_SUPPLY - total_supply(), 0.0),
        "max_supply": MAX_SUPPLY,
    }


def append_block(transactions):
    previous_hash = ledger["blocks"][-1]["hash"] if ledger["blocks"] else "0"
    block = {
        "index": len(ledger["blocks"]),
        "timestamp": utc_timestamp(),
        "previous_hash": previous_hash,
        "transactions": transactions,
        "nonce": len(ledger["blocks"]) + 1,
    }
    block["hash"] = hash_block(block)
    ledger["blocks"].append(block)
    return block


def create_genesis_block():
    genesis = {
        "index": 0,
        "timestamp": utc_timestamp(),
        "previous_hash": "0",
        "transactions": [
            {
                "type": "Genesis",
                "value": f"+{GENESIS_UNTOUCHABLE_SUPPLY:.4f}",
                "amount": f"+${(wallet_state['price'] * GENESIS_UNTOUCHABLE_SUPPLY):,.2f}",
                "note": "Genesis reserve minted (untouchable)",
                "time": "Just now",
                "positive": True,
                "recipient": wallet_state["walletAddress"],
                "memo": "1M untouchable genesis reserve",
            }
        ],
        "nonce": 1,
    }
    genesis["hash"] = hash_block(genesis)
    ledger["blocks"].append(genesis)


def sync_active_wallet(wallet):
    profile, _ = consensus_profile(wallet.get("consensusMode", DEFAULT_CONSENSUS_MODE))
    current_price = float(wallet.get("price", wallet_state.get("price", BASE_NETWORK_PRICE)))
    if current_price <= 0.0:
        current_price = market_price_for_supply() or BASE_NETWORK_PRICE
    wallet_state.update(
        {
            "name": wallet.get("name", "Bitmini Wallet"),
            "username": wallet.get("username"),
            "symbol": wallet.get("symbol", "BMINI"),
            "balance": float(wallet.get("balance", 0.0)),
            "price": current_price,
            "fiatValue": float(wallet.get("balance", 0.0)) * current_price,
            "marketVolumeUsd": float(wallet_state.get("marketVolumeUsd", 0.0)),
            "walletAddress": wallet["walletAddress"],
            "walletUniqueId": wallet.get("walletUniqueId"),
            "userCategory": wallet.get("userCategory", "consumer"),
            "userCategories": wallet.get("userCategories", [wallet.get("userCategory", "consumer")]),
            "referralCode": wallet.get("referralCode"),
            "referredBy": wallet.get("referredBy"),
            "referralEarnings": float(wallet.get("referralEarnings", 0.0)),
            "referralActivated": bool(wallet.get("referralActivated", False)),
            "referralMonthly": wallet.get("referralMonthly", {}),
            "mode": wallet.get("mode", "New wallet"),
            "consensusMode": wallet.get("consensusMode", DEFAULT_CONSENSUS_MODE),
            "consensusLabel": profile["label"],
            "stakedBalance": float(wallet.get("stakedBalance", 0.0)),
            "slashedTotal": float(wallet.get("slashedTotal", 0.0)),
            "lockedBalance": float(wallet.get("lockedBalance", 0.0)),
            "status": wallet.get("status", "Registered"),
            "network": wallet.get("network", wallet_state["network"]),
            "transactions": wallet.get("transactions", wallet_state["transactions"]),
            "alerts": wallet.get("alerts", wallet_state["alerts"]),
            "contacts": wallet.get("contacts", wallet_state["contacts"]),
        }
    )


def create_wallet_record(name="New User", email=None, password=None, date_of_birth=None, zip_code=None, username=None, user_category=None):
    wallet_address = generate_wallet_address()
    referral_code = generate_referral_code()
    seed_words = [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "omega",
        "luna",
        "atlas",
        "nova",
        "quartz",
        "orbit",
        "pixel",
        "ember",
        "petal",
        "cinder",
        "storm",
        "echo",
    ]
    seed_phrase = " ".join(secrets.choice(seed_words) for _ in range(12))
    private_key = ed25519_generate_private_hex()
    network_public_key = ed25519_public_hex_from_private(private_key)
    auth_salt = secrets.token_hex(16)
    resolved_password = str(password or "").strip() or secrets.token_hex(8)
    resolved_dob = str(date_of_birth or "").strip()
    resolved_zip = str(zip_code or "").strip()
    wallet_unique_id = generate_wallet_unique_id(name or "new user", resolved_dob, resolved_zip, email or "")
    encrypted_private_key = encrypt_secret(private_key, resolved_password, auth_salt)
    encrypted_seed_phrase = encrypt_secret(seed_phrase, resolved_password, auth_salt)
    normalized_category = normalize_user_category(user_category)
    wallet = {
        "name": name or "New User",
        "username": normalize_username(username) or None,
        "email": email or f"{(name or 'new-user').lower().replace(' ', '-')}@bitmini.local",
        "role": "user",
        "userCategory": normalized_category,
        "userCategories": [normalized_category],
        "dateOfBirth": resolved_dob,
        "zipCode": resolved_zip,
        "walletAddress": wallet_address,
        "walletUniqueId": wallet_unique_id,
        "referralCode": referral_code,
        "referredBy": None,
        "referralEarnings": 0.0,
        "referralActivated": False,
        "referralMonthly": {},
        "authSalt": auth_salt,
        "passcodeHash": hash_passcode(resolved_password, auth_salt),
        "seedPhraseHash": hash_seed_phrase(seed_phrase),
        "networkPublicKey": network_public_key,
        "securityMethods": ["password", "seed_phrase", "session_token"],
        "sessions": [],
        "auditLog": [],
        "failedLoginAttempts": 0,
        "loginLockedUntil": 0,
        "encryptedPrivateKey": encrypted_private_key,
        "encryptedSeedPhrase": encrypted_seed_phrase,
        "symbol": "BMINI",
        "balance": 0.0,
        "price": wallet_state["price"],
        "fiatValue": 0.0,
        "mode": "New wallet",
        "consensusMode": wallet_state.get("consensusMode", DEFAULT_CONSENSUS_MODE),
        "stakedBalance": 0.0,
        "slashedTotal": 0.0,
        "saleHistory": [],
        "withdrawalRequests": [],
        "lockedBalance": 0.0,
        "lastValidatedEpoch": 0,
        "status": "Registered",
        "network": "Bitmini Testnet",
        "createdAt": utc_timestamp(),
        "lastActiveAt": utc_timestamp(),
        "transactions": [
            {
                "type": "Genesis",
                "value": "+0.0000",
                "amount": "+$0.00",
                "note": "Wallet created",
                "time": "Just now",
                "positive": True,
                "recipient": wallet_address,
                "memo": "New wallet registration",
            }
        ],
        "alerts": wallet_state["alerts"],
        "contacts": wallet_state["contacts"],
    }
    wallet["fiatValue"] = wallet["balance"] * wallet["price"]
    wallets[wallet_address] = wallet
    sync_active_wallet(wallet)
    invalidate_epoch_cache()
    save_state_to_db()
    return wallet


def get_wallet(wallet_address):
    address = str(wallet_address or wallet_state["walletAddress"]).strip()
    if address in wallets:
        return wallets[address], address
    return None, address


def get_wallet_by_referral_code(referral_code):
    normalized = str(referral_code or "").strip().upper()
    if not normalized:
        return None
    for wallet in wallets.values():
        if str(wallet.get("referralCode", "")).upper() == normalized:
            return wallet
    return None


def issue_consensus_reward(wallet, wallet_address, reward, tx_type, note, memo):
    wallet["balance"] = round_coin(float(wallet.get("balance", 0.0)) + float(reward))
    wallet["fiatValue"] = wallet["balance"] * wallet_state["price"]
    tx = {
        "type": tx_type,
        "value": f"+{float(reward):.{COIN_DECIMALS}f}",
        "amount": f"+${(wallet_state['price'] * reward):,.2f}",
        "note": note,
        "time": "Now",
        "positive": True,
        "recipient": wallet_address,
        "memo": memo,
    }
    wallet.setdefault("transactions", [])
    wallet["transactions"].insert(0, tx)
    sync_active_wallet(wallet)
    block = append_block([tx])
    return tx, block


def credit_wallet(wallet, wallet_address, amount, tx_type, note, memo):
    wallet["balance"] = round_coin(float(wallet.get("balance", 0.0)) + float(amount))
    wallet["fiatValue"] = wallet["balance"] * wallet_state["price"]
    tx = {
        "type": tx_type,
        "value": f"+{float(amount):.{COIN_DECIMALS}f}",
        "amount": f"+${(wallet_state['price'] * amount):,.2f}",
        "note": note,
        "time": "Now",
        "positive": True,
        "recipient": wallet_address,
        "memo": memo,
    }
    wallet.setdefault("transactions", [])
    wallet["transactions"].insert(0, tx)
    sync_active_wallet(wallet)
    block = append_block([tx])
    return tx, block


def validator_score(epoch, wallet_address, staked_balance):
    seed = f"{epoch}:{wallet_address}:{staked_balance:.4f}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    return int(digest[:12], 16) + int(staked_balance * 1000)


def eligible_validators(mode):
    profile, normalized = consensus_profile(mode)
    min_stake = float(profile["stake_required"])
    eligible = []
    for wallet in wallets.values():
        stake = float(wallet.get("stakedBalance", 0.0))
        if normalized == "pow" or stake >= min_stake:
            eligible.append(wallet)
    return eligible, profile, normalized


def get_epoch_selection(mode):
    eligible, profile, normalized = eligible_validators(mode)
    epoch = int(validator_state.get("epoch", 1))
    selected_map = validator_state.setdefault("selected", {})
    epoch_key = str(epoch)

    cached = selected_map.get(epoch_key, {}).get(normalized)
    if cached is not None:
        return cached, epoch, profile, normalized

    sorted_wallets = sorted(
        eligible,
        key=lambda wallet: validator_score(epoch, wallet["walletAddress"], float(wallet.get("stakedBalance", 0.0))),
        reverse=True,
    )
    seats = 3 if normalized == "dpos" else 1
    selected = [wallet["walletAddress"] for wallet in sorted_wallets[:seats]]
    selected_map.setdefault(epoch_key, {})[normalized] = selected
    return selected, epoch, profile, normalized


def maybe_advance_epoch():
    validated_count = int(validator_state.get("validatedCount", 0))
    if validated_count > 0 and validated_count % EPOCH_LENGTH == 0:
        validator_state["epoch"] = int(validator_state.get("epoch", 1)) + 1


def invalidate_epoch_cache():
    validator_state["selected"] = {}


def slash_wallet(wallet, wallet_address, reason, penalty=None):
    staked = float(wallet.get("stakedBalance", 0.0))
    if staked <= 0:
        return None, None, 0.0

    calculated_penalty = penalty if penalty is not None else max(MIN_SLASH, round(staked * SLASH_RATE, 4))
    calculated_penalty = min(staked, float(calculated_penalty))

    wallet["stakedBalance"] = round(staked - calculated_penalty, 4)
    wallet["slashedTotal"] = round(float(wallet.get("slashedTotal", 0.0)) + calculated_penalty, 4)
    wallet["fiatValue"] = wallet["balance"] * wallet_state["price"]

    tx = {
        "type": "Slashed",
        "value": f"-{calculated_penalty:.4f}",
        "amount": f"-${(wallet_state['price'] * calculated_penalty):,.2f}",
        "note": f"Slashing penalty: {reason}",
        "time": "Now",
        "positive": False,
        "recipient": wallet_address,
        "memo": reason,
    }
    wallet.setdefault("transactions", [])
    wallet["transactions"].insert(0, tx)
    validator_state["slashEvents"] = int(validator_state.get("slashEvents", 0)) + 1
    sync_active_wallet(wallet)
    invalidate_epoch_cache()
    block = append_block([tx])
    return tx, block, calculated_penalty


def reset_runtime_state(persist=True):
    global wallet_state, wallets, ledger, validator_state
    wallet_state.clear()
    wallet_state.update(default_wallet_state())
    wallets.clear()
    ledger.clear()
    ledger.update({"blocks": []})
    validator_state.clear()
    validator_state.update(default_validator_state())

    create_genesis_block()
    wallet_state["fiatValue"] = wallet_state["balance"] * wallet_state["price"]
    genesis_private_key = "1f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100"
    wallets[wallet_state["walletAddress"]] = {
        "name": wallet_state["name"],
        "username": "@genesis",
        "role": "admin",
        "email": "genesis@bitmini.local",
        "userCategory": "validator",
        "userCategories": ["validator", "promoter", "advertiser"],
        "dateOfBirth": "1970-01-01",
        "zipCode": "00000",
        "walletAddress": wallet_state["walletAddress"],
        "walletUniqueId": "BM-GENESIS000000000000",
        "referralCode": "RGENESIS00",
        "referredBy": None,
        "referralEarnings": 0.0,
        "referralActivated": True,
        "referralMonthly": {},
        "authSalt": "genesis-salt",
        "passcodeHash": hash_passcode("genesis123", "genesis-salt"),
        "seedPhraseHash": hash_seed_phrase("genesis seed phrase"),
        "networkPublicKey": ed25519_public_hex_from_private(genesis_private_key),
        "securityMethods": ["password", "seed_phrase", "session_token"],
        "sessions": [],
        "encryptedPrivateKey": encrypt_secret(genesis_private_key, "genesis123", "genesis-salt"),
        "encryptedSeedPhrase": encrypt_secret("genesis seed phrase", "genesis123", "genesis-salt"),
        "balance": wallet_state["balance"],
        "symbol": wallet_state["symbol"],
        "network": wallet_state["network"],
        "transactions": wallet_state["transactions"],
        "createdAt": utc_timestamp(),
        "lastActiveAt": utc_timestamp(),
        "alerts": wallet_state["alerts"],
        "contacts": wallet_state["contacts"],
        "consensusMode": wallet_state["consensusMode"],
        "stakedBalance": wallet_state["stakedBalance"],
        "slashedTotal": wallet_state["slashedTotal"],
        "saleHistory": [],
        "withdrawalRequests": [],
        "lockedBalance": wallet_state.get("lockedBalance", GENESIS_UNTOUCHABLE_SUPPLY),
        "lastValidatedEpoch": 0,
        "status": "Verified",
        "mode": "Genesis block",
    }

    if persist:
        save_state_to_db()


def ensure_wallet_security_fields():
    updated = False
    ads_market = wallet_state.setdefault("adsMarketplace", {"ads": []})
    if not isinstance(ads_market.get("ads"), list):
        ads_market["ads"] = []
        updated = True

    for ad in ads_market.get("ads", []):
        ad.setdefault("id", f"AD-{secrets.token_hex(6).upper()}")
        ad_type = normalize_ad_type(ad.get("adType"))
        if ad_type not in AD_ALLOWED_TYPES:
            ad["adType"] = "site"
            updated = True
        ad.setdefault("title", "Untitled ad")
        ad.setdefault("description", "")
        ad.setdefault("mediaUrl", "")
        ad.setdefault("targetUrl", "")
        ad.setdefault("viewers", [])
        ad.setdefault("viewCount", len(ad.get("viewers", [])))
        ad.setdefault("totalSpent", 0.0)
        ad.setdefault("createdAt", utc_timestamp())
        ad.setdefault("updatedAt", ad.get("createdAt"))
        ad.setdefault("status", "active")
        ad.setdefault("budgetTotal", float(ad.get("budgetRemaining", 0.0)))
        ad.setdefault("budgetRemaining", float(ad.get("budgetTotal", 0.0)))

    for wallet in wallets.values():
        if not wallet.get("authSalt"):
            wallet["authSalt"] = secrets.token_hex(16)
            updated = True
        if not wallet.get("passcodeHash"):
            wallet["passcodeHash"] = hash_passcode("bitmini123", wallet["authSalt"])
            updated = True
        if not wallet.get("seedPhraseHash") and wallet.get("seedPhrase"):
            wallet["seedPhraseHash"] = hash_seed_phrase(wallet.get("seedPhrase"))
            updated = True
        if not wallet.get("encryptedPrivateKey"):
            legacy_private = str(wallet.get("privateKey", "") or "").strip()
            if not legacy_private:
                legacy_private = ed25519_generate_private_hex()
            wallet["encryptedPrivateKey"] = encrypt_secret(legacy_private, "bitmini123", wallet["authSalt"])
            updated = True
        if not wallet.get("networkPublicKey"):
            try:
                default_private = decrypt_secret(wallet.get("encryptedPrivateKey", ""), "bitmini123", wallet["authSalt"])
                wallet["networkPublicKey"] = ed25519_public_hex_from_private(default_private)
            except Exception:
                wallet["networkPublicKey"] = ""
            updated = True
        if not wallet.get("securityMethods"):
            wallet["securityMethods"] = ["password", "seed_phrase", "session_token"]
            updated = True
        if not wallet.get("walletUniqueId"):
            wallet["walletUniqueId"] = generate_wallet_unique_id(
                wallet.get("name", "new user"),
                wallet.get("dateOfBirth", "1970-01-01"),
                wallet.get("zipCode", "00000"),
                wallet.get("email", "legacy@bitmini.local"),
            )
            updated = True
        if not wallet.get("username"):
            local_name = re.sub(r"[^a-z0-9._-]", "", str(wallet.get("name", "user")).strip().lower().replace(" ", ""))
            normalized = normalize_username(local_name[:24] if local_name else "user")
            if normalized:
                wallet["username"] = normalized
                updated = True
        wallet.setdefault("dateOfBirth", "1970-01-01")
        wallet.setdefault("zipCode", "00000")
        wallet.setdefault("sessions", [])
        wallet.setdefault("referralActivated", not bool(wallet.get("referredBy")))
        wallet.setdefault("referralMonthly", {})
        wallet.setdefault("referralRewardCountMonthly", {})
        normalized_category = normalize_user_category(wallet.get("userCategory", "consumer"))
        if wallet.get("userCategory") != normalized_category:
            wallet["userCategory"] = normalized_category
            updated = True
        category_set = set(wallet.get("userCategories", []))
        if not category_set:
            category_set = {normalized_category}
            updated = True
        if normalized_category not in category_set:
            category_set.add(normalized_category)
            updated = True
        wallet["userCategories"] = sorted(category_set)
        wallet.setdefault("lastActiveAt", wallet.get("createdAt", utc_timestamp()))
        wallet.setdefault("lockedBalance", 0.0)
        if wallet.get("mode") == "Genesis block":
            wallet["lockedBalance"] = max(float(wallet.get("lockedBalance", 0.0)), GENESIS_UNTOUCHABLE_SUPPLY)
            wallet["balance"] = max(float(wallet.get("balance", 0.0)), wallet["lockedBalance"])
            updated = True
    if updated:
        save_state_to_db()


def initialize_runtime():
    init_storage()
    if not load_state_from_db():
        reset_runtime_state(persist=True)
    ensure_wallet_security_fields()


initialize_runtime()


@app.after_request
def set_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'"
    )
    return response


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"ok": False, "error": "Route not found."}), 404


@app.errorhandler(500)
def server_error(_error):
    return jsonify({"ok": False, "error": "The Bitmini server encountered an unexpected error."}), 500


@app.get("/")
def home():
    return render_template("home.html", login_required=request.args.get("login_required") == "1")


@app.get("/tour")
def guided_tour_page():
    return render_template("tour.html")


@app.get("/donate")
def donation_page():
    return render_template("donate.html")


@app.get("/app")
def wallet_app():
    requested_wallet = str(request.args.get("wallet") or "").strip()
    session_token = str(request.args.get("session") or "").strip()
    if not requested_wallet or not session_token:
        return redirect(url_for("home", login_required="1"))

    wallet, wallet_address = get_wallet(requested_wallet)
    if not wallet or wallet_address != requested_wallet:
        return redirect(url_for("home", login_required="1"))

    if not get_wallet_from_session(session_token):
        return redirect(url_for("home", login_required="1"))

    return render_template("index.html", wallet=wallet)


@app.get("/whitepaper")
def whitepaper_page():
    return render_template("whitepaper.html")


@app.get("/api/security-layer")
def security_layer_info():
    return jsonify(
        {
            "ok": True,
            "layers": [
                {
                    "name": "Wallet authentication",
                    "details": "Existing users login with wallet address or @username plus password (or seed phrase) before a session is created.",
                },
                {
                    "name": "Session authorization",
                    "details": "All write operations require a time-limited session token linked to one wallet.",
                },
                {
                    "name": "Wallet ownership checks",
                    "details": "Requests are blocked when the requested wallet address does not match the authenticated session wallet.",
                },
                {
                    "name": "Policy controls",
                    "details": "Encrypted wallet secrets, self-send blocking, duplicate-payment detection, supply cap limits, and slashing are enforced by backend rules.",
                },
            ],
        }
    )


@app.get("/api/network/public")
def public_phase_a_status():
    return jsonify(phase_a_public_testnet_config())


@app.get("/api/network/bootstrap")
@app.get("/api/launch/phase-a")
@app.get("/api/launch/phase-b")
def public_phase_b_status():
    return jsonify(phase_b_bootstrap_config())


@app.get("/api/network/peers")
def network_peer_registry():
    payload = phase_b_bootstrap_config()
    return jsonify({"ok": True, "phase": payload["phase"], "status": payload["status"], "peers": payload["peers"]})


@app.post("/api/network/peers/register")
def register_network_peer():
    payload = request.get_json(silent=True) or {}
    peer_url = str(payload.get("url") or payload.get("peerUrl") or "").strip().rstrip("/")
    if not peer_url:
        return jsonify({"ok": False, "error": "A peer URL is required."}), 400

    config = phase_b_bootstrap_config()
    peers = list(dict.fromkeys([*config["peers"], peer_url]))
    NETWORK_PEER_STATE["peers"] = peers
    NETWORK_PEER_STATE["bootstrapPeers"] = peers
    config["peers"] = peers
    config["bootstrapPeers"] = peers
    return jsonify({"ok": True, "phase": config["phase"], "status": config["status"], "peers": peers})


@app.get("/api/network/health")
def network_health():
    status, payload = node_rpc_request("GET", "/rpc/health")
    if status == 503:
        payload = {
            "ok": True,
            "network": wallet_state.get("network", "Bitmini Testnet"),
            "status": DEFAULT_TESTNET_STATUS,
            "phase": DEFAULT_PHASE,
            "chainId": str(os.environ.get("BITMINI_CHAIN_ID", DEFAULT_CHAIN_ID)).strip() or DEFAULT_CHAIN_ID,
            "nodeRpc": "not-configured",
            "message": "Node RPC is not configured for this public testnet bootstrap yet.",
        }
    return jsonify(payload), status


@app.get("/api/network/token-metrics")
def network_token_metrics():
    status, payload = node_rpc_request("GET", "/rpc/token-metrics")
    return jsonify(payload), status


@app.post("/api/network/validators/update")
def network_validator_update():
    payload = request.get_json(silent=True) or {}
    _, _, auth_error = authorize_admin_request(payload)
    if auth_error:
        return auth_error

    status, response = node_rpc_request("POST", "/rpc/validators/update", payload)
    return jsonify(response), status


@app.get("/api/qr")
def qr_code_image():
    payload = str(request.args.get("value") or request.args.get("address") or "").strip()
    if not payload:
        payload = f"bitmini:{wallet_state.get('walletAddress', 'BMINI-ADDRESS')}"
    if not payload.startswith("bitmini:") and not payload.startswith("B"):
        payload = f"bitmini:{payload}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#081c1a", back_color="#f4f7f6")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.get("/api/wallet")
def wallet_api():
    address = request.args.get("address")
    if address:
        wallet, _ = get_wallet(address)
        if not wallet:
            return jsonify({"ok": False, "error": "Wallet not found."}), 404
        wallet["fiatValue"] = wallet["balance"] * wallet_state["price"]
        return jsonify(wallet_public_payload(wallet))

    wallet_state["fiatValue"] = wallet_state["balance"] * wallet_state["price"]
    return jsonify(wallet_public_payload(wallet_state))


@app.get("/api/wallet/download")
def wallet_download():
    requested_address = str(request.args.get("address") or "").strip()
    session_token = request.headers.get("X-Bitmini-Session") or str(request.args.get("session") or "").strip()
    wallet = get_wallet_from_session(session_token)
    if not wallet:
        return jsonify({"ok": False, "error": "Authentication required to download wallet."}), 401

    session_wallet_address = wallet.get("walletAddress")
    if requested_address and requested_address != session_wallet_address:
        return jsonify({"ok": False, "error": "Forbidden for this wallet session."}), 403

    payload = wallet_download_payload(wallet)
    response = Response(json.dumps(payload, indent=2), mimetype="application/json")
    file_name = f"{(wallet.get('name', 'bitmini-wallet').replace(' ', '-')).lower()}.json"
    response.headers["Content-Disposition"] = f"attachment; filename={file_name}"
    return response


@app.get("/api/health")
def health():
    return jsonify(
        {
            "ok": True,
            "status": "ok",
            "symbol": "BMINI",
            "network": wallet_state.get("network", "Bitmini Testnet"),
            "phase": DEFAULT_PHASE,
            "statusText": DEFAULT_TESTNET_STATUS,
            "blocks": len(ledger.get("blocks", [])),
            "epoch": validator_state.get("epoch", 1),
            "timestamp": utc_timestamp(),
            "wallets": {
                "total": len(wallets),
                "active24h": sum(
                    1
                    for wallet in wallets.values()
                    if wallet.get("lastActiveAt")
                    and (current_epoch_seconds() - int(datetime.fromisoformat(str(wallet["lastActiveAt"]).replace("Z", "+00:00")).timestamp()) < 86400)
                ),
            },
            "version": "beta-1.0",
        }
    )


@app.get("/api/ledger")
def ledger_api():
    return jsonify({"blocks": ledger["blocks"], "count": len(ledger["blocks"])})


@app.get("/api/transactions/recent")
def recent_transactions_api():
    try:
        limit = int(request.args.get("limit", 10) or 10)
    except ValueError:
        limit = 10
    limit = max(min(limit, 50), 1)
    return jsonify(
        {
            "ok": True,
            "count": limit,
            "transactions": recent_ledger_transactions(limit=limit),
        }
    )


@app.get("/api/leaderboards")
def leaderboards_api():
    try:
        limit = int(request.args.get("limit", 10) or 10)
    except ValueError:
        limit = 10
    limit = max(min(limit, 25), 1)

    payload = {
        "ok": True,
        "generatedAt": utc_timestamp(),
        "limit": limit,
        "topReferralEarners": {
            "daily": top_referral_earners_since(timedelta(days=1), limit=limit),
            "weekly": top_referral_earners_since(timedelta(days=7), limit=limit),
            "monthly": top_referral_earners_since(timedelta(days=30), limit=limit),
        },
        "topAdSpenders": top_ad_spenders(limit=limit),
        "topContributors": top_wallet_metric("contributors", limit=limit),
        "topEarners": top_wallet_metric("earners", limit=limit),
        "topTrade": top_wallet_metric("trade", limit=limit),
    }
    return jsonify(payload)


def sqlite_health_snapshot():
    db_exists = os.path.exists(DB_PATH)
    snapshot = {
        "path": DB_PATH,
        "exists": db_exists,
        "sizeBytes": os.path.getsize(DB_PATH) if db_exists else 0,
        "rowCount": 0,
        "keys": [],
        "lastModified": None,
    }

    if db_exists:
        snapshot["lastModified"] = datetime.fromtimestamp(
            os.path.getmtime(DB_PATH), timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT key FROM state_store ORDER BY key").fetchall()
            snapshot["keys"] = [row[0] for row in rows]
            snapshot["rowCount"] = len(rows)

    return snapshot


def build_token_metrics():
    now = datetime.now(timezone.utc)
    day_window = 24 * 60 * 60
    week_window = 7 * 24 * 60 * 60

    active_24h = 0
    active_7d = 0
    circulating = 0.0
    locked = 0.0

    for wallet in wallets.values():
        balance = float(wallet.get("balance", 0.0))
        staked = float(wallet.get("stakedBalance", 0.0))
        locked_balance = float(wallet.get("lockedBalance", 0.0))
        circulating += max(balance - locked_balance, 0.0) + staked
        locked += locked_balance

        last_active = parse_utc_timestamp(wallet.get("lastActiveAt") or wallet.get("createdAt"))
        if last_active is None:
            continue
        age_seconds = (now - last_active).total_seconds()
        if age_seconds <= day_window:
            active_24h += 1
        if age_seconds <= week_window:
            active_7d += 1

    minted = total_supply()
    remaining = max(MAX_SUPPLY - minted, 0.0)
    effective_cap = current_network_capacity()
    return {
        "supply": {
            "minted": round(minted, 4),
            "max": MAX_SUPPLY,
            "effectiveMax": round(effective_cap, 4),
            "remaining": round(remaining, 4),
            "circulating": round(circulating, 4),
            "locked": round(locked, 4),
            "lockedGenesisReserve": GENESIS_UNTOUCHABLE_SUPPLY,
        },
        "wallets": {
            "total": len(wallets),
            "active24h": active_24h,
            "active7d": active_7d,
        },
        "network": {
            "price": round(market_price_for_supply(), 4),
            "capacityExpansionEveryDays": CAPACITY_EXPANSION_INTERVAL_DAYS,
            "rewardHalvingEveryYears": REWARD_HALVING_INTERVAL_DAYS // 365,
        },
    }


@app.get("/api/token-metrics")
def token_metrics_api():
    return jsonify({"ok": True, **build_token_metrics()})


@app.get("/api/admin")
def admin_dashboard_data():
    wallet, _, auth_error = authorize_admin_request()
    if auth_error:
        return auth_error

    active_mode = wallet_state.get("consensusMode", DEFAULT_CONSENSUS_MODE)
    selected, epoch, profile, normalized = get_epoch_selection(active_mode)
    slash_txs = []

    for block in reversed(ledger["blocks"]):
        for tx in block.get("transactions", []):
            if tx.get("type") == "Slashed":
                slash_txs.append(
                    {
                        "blockIndex": block.get("index"),
                        "timestamp": block.get("timestamp"),
                        "recipient": tx.get("recipient"),
                        "value": tx.get("value"),
                        "memo": tx.get("memo"),
                        "note": tx.get("note"),
                    }
                )
            if len(slash_txs) >= 20:
                break
        if len(slash_txs) >= 20:
            break

    pending_withdrawals = []
    for candidate_wallet in wallets.values():
        for request_entry in candidate_wallet.get("withdrawalRequests", []):
            if str(request_entry.get("status", "")).lower() == "pending":
                pending_withdrawals.append(
                    {
                        "walletAddress": candidate_wallet.get("walletAddress"),
                        "name": candidate_wallet.get("name", "Unknown"),
                        "withdrawalId": request_entry.get("id"),
                        "amountUsd": request_entry.get("amountUsd"),
                        "method": request_entry.get("method"),
                        "destination": request_entry.get("destination"),
                        "createdAt": request_entry.get("createdAt"),
                    }
                )

    return jsonify(
        {
            "ok": True,
            "network": wallet_state.get("network", "Bitmini Testnet"),
            "supply": {
                "current": total_supply(),
                "max": MAX_SUPPLY,
                "remaining": max(MAX_SUPPLY - total_supply(), 0.0),
            },
            "tokenMetrics": build_token_metrics(),
            "epoch": {
                "current": epoch,
                "length": EPOCH_LENGTH,
                "validatedCount": int(validator_state.get("validatedCount", 0)),
                "slashEvents": int(validator_state.get("slashEvents", 0)),
                "consensusMode": normalized,
                "consensusLabel": profile["label"],
                "selectedValidators": selected,
            },
            "pendingWithdrawals": pending_withdrawals,
            "slashHistory": slash_txs,
            "sqlite": sqlite_health_snapshot(),
            "ledger": {
                "blockCount": len(ledger["blocks"]),
            },
        }
    )


@app.post("/api/withdrawal/approve")
def approve_withdrawal_request():
    payload = request.get_json(silent=True) or {}
    _, admin_address, auth_error = authorize_admin_request({})
    if auth_error:
        return auth_error

    target_address = str(payload.get("walletAddress") or payload.get("targetWalletAddress") or "").strip()
    if not target_address:
        return jsonify({"ok": False, "error": "Target wallet address is required."}), 400

    target_wallet, _ = get_wallet(target_address)
    if not target_wallet:
        return jsonify({"ok": False, "error": "Target wallet not found."}), 404

    withdrawal_id = str(payload.get("withdrawalId") or "").strip()
    if not withdrawal_id:
        return jsonify({"ok": False, "error": "Withdrawal ID is required."}), 400

    for entry in target_wallet.get("withdrawalRequests", []):
        if str(entry.get("id")) == withdrawal_id:
            if str(entry.get("status", "")).lower() != "pending":
                return jsonify({"ok": False, "error": "Withdrawal is not pending approval."}), 400
            entry["status"] = "approved"
            entry["approvedBy"] = admin_address
            entry["approvedAt"] = utc_timestamp()
            touch_wallet_activity(target_wallet)
            save_state_to_db()
            return jsonify({"ok": True, "message": "Withdrawal approved.", "withdrawal": entry})

    return jsonify({"ok": False, "error": "Withdrawal request not found."}), 404


@app.post("/api/withdrawal/reject")
def reject_withdrawal_request():
    payload = request.get_json(silent=True) or {}
    _, admin_address, auth_error = authorize_admin_request({})
    if auth_error:
        return auth_error

    target_address = str(payload.get("walletAddress") or payload.get("targetWalletAddress") or "").strip()
    if not target_address:
        return jsonify({"ok": False, "error": "Target wallet address is required."}), 400

    target_wallet, _ = get_wallet(target_address)
    if not target_wallet:
        return jsonify({"ok": False, "error": "Target wallet not found."}), 404

    withdrawal_id = str(payload.get("withdrawalId") or "").strip()
    if not withdrawal_id:
        return jsonify({"ok": False, "error": "Withdrawal ID is required."}), 400

    for entry in target_wallet.get("withdrawalRequests", []):
        if str(entry.get("id")) == withdrawal_id:
            if str(entry.get("status", "")).lower() != "pending":
                return jsonify({"ok": False, "error": "Withdrawal is not pending approval."}), 400
            entry["status"] = "rejected"
            entry["rejectedBy"] = admin_address
            entry["rejectedAt"] = utc_timestamp()
            entry["rejectReason"] = str(payload.get("reason") or "Manual review rejected the request.")
            touch_wallet_activity(target_wallet)
            save_state_to_db()
            return jsonify({"ok": True, "message": "Withdrawal rejected.", "withdrawal": entry})

    return jsonify({"ok": False, "error": "Withdrawal request not found."}), 404


@app.get("/api/referrals")
def referral_dashboard_data():
    address = str(request.args.get("address") or wallet_state["walletAddress"]).strip()
    wallet, _ = get_wallet(address)
    if not wallet:
        return jsonify({"ok": False, "error": "Wallet not found."}), 404

    invited_wallets = [
        {
            "walletAddress": candidate.get("walletAddress"),
            "name": candidate.get("name", "Unknown"),
            "createdAt": candidate.get("createdAt"),
        }
        for candidate in wallets.values()
        if candidate.get("referredBy") == address
    ]

    history = []
    for block in reversed(ledger["blocks"]):
        for tx in block.get("transactions", []):
            if tx.get("type") == "Referral" and tx.get("recipient") == address:
                history.append(
                    {
                        "blockIndex": block.get("index"),
                        "timestamp": block.get("timestamp"),
                        "value": tx.get("value"),
                        "note": tx.get("note"),
                        "memo": tx.get("memo"),
                    }
                )
            if len(history) >= 50:
                break
        if len(history) >= 50:
            break

    return jsonify(
        {
            "ok": True,
            "walletAddress": address,
            "referralCode": wallet.get("referralCode"),
            "referredBy": wallet.get("referredBy"),
            "lifetimeEarnings": float(wallet.get("referralEarnings", 0.0)),
            "monthlyEarnings": monthly_referral_earned(wallet),
            "monthlyCap": REFERRAL_MONTHLY_CAP,
            "monthlyRemaining": referral_cap_remaining(wallet),
            "monthlyRewardEvents": monthly_referral_reward_count(wallet),
            "nextRewardMultiplier": referral_reward_multiplier_for_wallet(wallet),
            "rewardTiers": [
                {
                    "upToMonthlyEvents": None if max_count == float("inf") else int(max_count),
                    "multiplier": float(multiplier),
                }
                for max_count, multiplier in REFERRAL_REWARD_TIERS
            ],
            "rewardModel": "Unlimited invites with progressive reward multipliers that taper as monthly referral events increase.",
            "pendingActivation": bool(wallet.get("referredBy") and not wallet.get("referralActivated")),
            "invitedCount": len(invited_wallets),
            "invitedFriends": invited_wallets,
            "history": history,
        }
    )


@app.post("/api/wallet/category")
def set_wallet_category():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    requested = str(payload.get("userCategory") or payload.get("category") or "").strip().lower()
    if requested not in USER_CATEGORIES:
        return jsonify({"ok": False, "error": "Category must be one of: consumer, validator, promoter, advertiser."}), 400

    wallet["userCategory"] = requested
    categories = set(wallet.get("userCategories", []))
    categories.add(requested)
    wallet["userCategories"] = sorted(categories)
    touch_wallet_activity(wallet)
    sync_active_wallet(wallet)
    save_state_to_db()
    return jsonify(
        {
            "ok": True,
            "message": f"Wallet category set to {requested}.",
            "walletAddress": wallet_address,
            "userCategory": requested,
            "userCategories": wallet.get("userCategories", []),
        }
    )


@app.get("/api/ads/market")
def ads_market_api():
    requested_address = str(request.args.get("address") or "").strip()
    payload = {"walletAddress": requested_address} if requested_address else {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    ordered_ads = ranked_ads_for_viewer(wallet_address)
    mine = [ad for ad in ordered_ads if ad.get("sellerWalletAddress") == wallet_address]
    return jsonify(
        {
            "ok": True,
            "walletAddress": wallet_address,
            "ads": ordered_ads,
            "myAds": mine,
            "topSpenders": top_ad_spenders(limit=10),
        }
    )


@app.post("/api/ads/create")
def create_ad_listing():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    wallet_category = normalize_user_category(wallet.get("userCategory", "consumer"))
    if wallet_category not in AD_SELLER_CATEGORIES:
        return jsonify(
            {
                "ok": False,
                "error": "Ad sellers must use promoter or advertiser wallet category.",
                "currentCategory": wallet_category,
                "allowedCategories": sorted(AD_SELLER_CATEGORIES),
            }
        ), 403

    ad_type = normalize_ad_type(payload.get("adType"))
    if ad_type not in AD_ALLOWED_TYPES:
        return jsonify({"ok": False, "error": "adType must be one of: video, site, poster."}), 400

    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    media_url = normalize_external_link(payload.get("mediaUrl"))
    target_url = normalize_external_link(payload.get("targetUrl"))

    if len(title) < 3:
        return jsonify({"ok": False, "error": "Ad title must be at least 3 characters."}), 400
    if not media_url and not target_url:
        return jsonify({"ok": False, "error": "Provide at least one ad link (mediaUrl or targetUrl)."}), 400

    bid_per_view = float(payload.get("bidPerView", 0) or 0)
    budget_total = float(payload.get("budgetTotal", 0) or 0)
    if bid_per_view < AD_MIN_BID_PER_VIEW or bid_per_view > AD_MAX_BID_PER_VIEW:
        return jsonify({"ok": False, "error": f"bidPerView must be between {AD_MIN_BID_PER_VIEW} and {AD_MAX_BID_PER_VIEW}."}), 400
    if budget_total < AD_MIN_BUDGET:
        return jsonify({"ok": False, "error": f"budgetTotal must be at least {AD_MIN_BUDGET}."}), 400
    if budget_total < bid_per_view:
        return jsonify({"ok": False, "error": "budgetTotal must be greater than or equal to bidPerView."}), 400

    unlocked_balance = max(float(wallet.get("balance", 0.0)) - float(wallet.get("lockedBalance", 0.0)), 0.0)
    if budget_total > unlocked_balance:
        return jsonify({"ok": False, "error": "Insufficient unlocked balance to fund ad budget."}), 400

    wallet["balance"] = round_coin(float(wallet.get("balance", 0.0)) - budget_total)
    ad = {
        "id": f"AD-{secrets.token_hex(6).upper()}",
        "sellerWalletAddress": wallet_address,
        "adType": ad_type,
        "title": title,
        "description": description,
        "mediaUrl": media_url,
        "targetUrl": target_url,
        "bidPerView": round_coin(bid_per_view),
        "budgetTotal": round_coin(budget_total),
        "budgetRemaining": round_coin(budget_total),
        "status": "active",
        "viewCount": 0,
        "viewers": [],
        "totalSpent": 0.0,
        "createdAt": utc_timestamp(),
        "updatedAt": utc_timestamp(),
    }
    ads_store().append(ad)

    debit_tx = make_ad_transaction(
        wallet=wallet,
        amount=budget_total,
        tx_type="Ad Budget",
        note=f"Ad funded: {title}",
        memo=f"{ad_type} campaign budget",
        positive=False,
    )
    append_block([debit_tx])
    save_state_to_db()
    return jsonify(
        {
            "ok": True,
            "message": "Ad listing created and funded.",
            "ad": ad_payload_for_viewer(ad, viewer_address=wallet_address),
            "wallet": {
                "walletAddress": wallet_address,
                "balance": wallet["balance"],
                "fiatValue": wallet.get("fiatValue", 0.0),
            },
        }
    )


@app.post("/api/ads/view")
def consume_ad_view():
    payload = request.get_json(silent=True) or {}
    viewer_wallet, viewer_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    ad_id = str(payload.get("adId") or "").strip()
    if not ad_id:
        return jsonify({"ok": False, "error": "adId is required."}), 400

    ad = next((candidate for candidate in ads_store() if str(candidate.get("id")) == ad_id), None)
    if not ad:
        return jsonify({"ok": False, "error": "Ad not found."}), 404

    if str(ad.get("sellerWalletAddress") or "") == viewer_address:
        return jsonify({"ok": False, "error": "Seller cannot claim views on own ad."}), 400

    viewers = ad_viewers(ad)
    if viewer_address in viewers:
        return jsonify({"ok": False, "error": "You already viewed this ad. Repeated views are blocked."}), 409

    if not ad_is_active_for_view(ad):
        ad["status"] = "completed"
        ad["updatedAt"] = utc_timestamp()
        save_state_to_db()
        return jsonify({"ok": False, "error": "Ad budget is exhausted or ad is no longer active."}), 400

    seller_wallet, _ = get_wallet(ad.get("sellerWalletAddress"))
    if not seller_wallet:
        return jsonify({"ok": False, "error": "Ad seller wallet not found."}), 404

    payout = round_coin(float(ad.get("bidPerView", 0.0)))
    if payout <= 0:
        return jsonify({"ok": False, "error": "Invalid ad payout configuration."}), 400
    if ad_budget_remaining(ad) < payout:
        ad["status"] = "completed"
        ad["updatedAt"] = utc_timestamp()
        save_state_to_db()
        return jsonify({"ok": False, "error": "Ad budget is exhausted."}), 400

    ad["budgetRemaining"] = round_coin(ad_budget_remaining(ad) - payout)
    ad["totalSpent"] = round_coin(float(ad.get("totalSpent", 0.0)) + payout)
    ad["viewCount"] = int(ad.get("viewCount", 0)) + 1
    viewers.append(viewer_address)
    ad["updatedAt"] = utc_timestamp()
    if ad_budget_remaining(ad) < float(ad.get("bidPerView", 0.0)):
        ad["status"] = "completed"

    viewer_wallet["balance"] = round_coin(float(viewer_wallet.get("balance", 0.0)) + payout)
    viewer_tx = make_ad_transaction(
        wallet=viewer_wallet,
        amount=payout,
        tx_type="Ad View Reward",
        note=f"Viewed ad: {ad.get('title')}",
        memo=f"{ad.get('adType')} ad reward",
        positive=True,
    )
    seller_tx = make_ad_transaction(
        wallet=seller_wallet,
        amount=payout,
        tx_type="Ad View Spend",
        note=f"Paid for view: {ad.get('title')}",
        memo=f"Viewer: {viewer_address}",
        positive=False,
    )
    append_block([viewer_tx, seller_tx])
    save_state_to_db()

    return jsonify(
        {
            "ok": True,
            "message": "Ad view recorded and reward credited.",
            "ad": ad_payload_for_viewer(ad, viewer_address=viewer_address),
            "reward": payout,
            "viewer": {
                "walletAddress": viewer_address,
                "balance": viewer_wallet.get("balance", 0.0),
                "fiatValue": viewer_wallet.get("fiatValue", 0.0),
            },
        }
    )


@app.get("/api/epoch")
def epoch_info():
    mode = request.args.get("mode") or wallet_state.get("consensusMode", DEFAULT_CONSENSUS_MODE)
    selected, epoch, profile, normalized = get_epoch_selection(mode)
    return jsonify(
        {
            "ok": True,
            "epoch": epoch,
            "epochLength": EPOCH_LENGTH,
            "mode": normalized,
            "consensusLabel": profile["label"],
            "selectedValidators": selected,
            "validatedCount": int(validator_state.get("validatedCount", 0)),
            "slashEvents": int(validator_state.get("slashEvents", 0)),
        }
    )


@app.get("/api/consensus")
def consensus_info():
    current_mode = wallet_state.get("consensusMode", DEFAULT_CONSENSUS_MODE)
    current_profile, _ = consensus_profile(current_mode)
    selected, epoch, _, _ = get_epoch_selection(current_mode)
    return jsonify(
        {
            "current": {
                "mode": current_mode,
                "label": current_profile["label"],
                "mobile_ready": current_profile["mobile_ready"],
                "energy": current_profile["energy"],
                "epoch": epoch,
                "selectedValidators": selected,
            },
            "profiles": CONSENSUS_PROFILES,
        }
    )


@app.post("/api/consensus")
def set_consensus_mode():
    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode") or "").strip().lower()
    profile, normalized = consensus_profile(mode)

    if normalized not in CONSENSUS_PROFILES:
        return jsonify({"ok": False, "error": "Unsupported consensus mode."}), 400

    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    wallet["consensusMode"] = normalized
    sync_active_wallet(wallet)
    invalidate_epoch_cache()
    save_state_to_db()

    selected, epoch, _, _ = get_epoch_selection(normalized)
    return jsonify(
        {
            "ok": True,
            "message": f"Consensus set to {profile['label']}.",
            "walletAddress": wallet_address,
            "consensus": {
                "mode": normalized,
                "label": profile["label"],
                "mobile_ready": profile["mobile_ready"],
                "energy": profile["energy"],
                "epoch": epoch,
                "selectedValidators": selected,
            },
        }
    )


@app.post("/api/stake")
def stake_tokens():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    amount = float(payload.get("amount", 0) or 0)
    if amount <= 0:
        return jsonify({"ok": False, "error": "Stake amount must be greater than zero."}), 400

    available_balance = float(wallet.get("balance", 0.0)) - float(wallet.get("lockedBalance", 0.0))
    if amount > available_balance:
        return jsonify({"ok": False, "error": "Insufficient unlocked balance to stake."}), 400

    wallet["balance"] = round(available_balance - amount, 4)
    wallet["stakedBalance"] = round(float(wallet.get("stakedBalance", 0.0)) + amount, 4)
    wallet["fiatValue"] = wallet["balance"] * wallet_state["price"]

    tx = {
        "type": "Staked",
        "value": f"-{amount:.4f}",
        "amount": f"-${(wallet_state['price'] * amount):,.2f}",
        "note": "Tokens locked for mobile validation",
        "time": "Now",
        "positive": False,
        "recipient": wallet_address,
        "memo": "Stake locked",
    }
    wallet.setdefault("transactions", [])
    wallet["transactions"].insert(0, tx)
    touch_wallet_activity(wallet)
    sync_active_wallet(wallet)
    invalidate_epoch_cache()
    block = append_block([tx])
    save_state_to_db()

    return jsonify(
        {
            "ok": True,
            "message": "Stake locked successfully.",
            "wallet": {
                "walletAddress": wallet_address,
                "balance": wallet["balance"],
                "lockedBalance": wallet.get("lockedBalance", 0.0),
                "stakedBalance": wallet["stakedBalance"],
                "fiatValue": wallet["fiatValue"],
            },
            "block_index": block["index"],
        }
    )


@app.post("/api/slash")
def slash_validator():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    reason = str(payload.get("reason") or "Validator misbehavior").strip() or "Validator misbehavior"
    requested_penalty = payload.get("penalty")
    penalty = float(requested_penalty) if requested_penalty is not None else None
    tx, block, penalty_applied = slash_wallet(wallet, wallet_address, reason, penalty=penalty)

    if tx is None:
        return jsonify({"ok": False, "error": "No staked balance available to slash."}), 400

    touch_wallet_activity(wallet)
    save_state_to_db()
    return jsonify(
        {
            "ok": True,
            "message": "Slashing penalty applied.",
            "penalty": penalty_applied,
            "wallet": {
                "walletAddress": wallet_address,
                "balance": wallet["balance"],
                "stakedBalance": wallet["stakedBalance"],
                "slashedTotal": wallet.get("slashedTotal", 0.0),
            },
            "block_index": block["index"],
        }
    )


@app.post("/api/validate")
def validate_block_reward():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    selected, epoch, profile, normalized = get_epoch_selection(wallet.get("consensusMode", DEFAULT_CONSENSUS_MODE))
    staked_balance = float(wallet.get("stakedBalance", 0.0))
    if staked_balance < profile["stake_required"]:
        return jsonify(
            {
                "ok": False,
                "error": f"{profile['label']} requires at least {profile['stake_required']:.4f} staked BMINI.",
            }
        ), 400

    if selected and wallet_address not in selected:
        return jsonify(
            {
                "ok": False,
                "error": "Wallet is not selected for the current epoch.",
                "epoch": epoch,
                "selectedValidators": selected,
            }
        ), 403

    if int(wallet.get("lastValidatedEpoch", 0)) == epoch:
        return jsonify({"ok": False, "error": "Validator already produced a block this epoch."}), 400

    if payload.get("fault"):
        _, block, penalty_applied = slash_wallet(wallet, wallet_address, "Fault reported during validation")
        if block is not None:
            save_state_to_db()
        return jsonify(
            {
                "ok": False,
                "error": "Validator fault recorded. Stake was slashed.",
                "penalty": penalty_applied,
            }
        ), 400

    requested_reward = payload.get("reward")
    base_reward, normalized, profile = effective_reward_for_mode(wallet.get("consensusMode", DEFAULT_CONSENSUS_MODE), requested_reward)
    if base_reward <= 0:
        return jsonify({"ok": False, "error": "Validation reward must be greater than zero."}), 400

    if total_supply() >= MAX_SUPPLY:
        return jsonify(
            {
                "ok": False,
                "error": "All coins have been minted. Network rewards now shift to fee and stake based issuance.",
                "issuanceMode": "fee_or_stake",
            }
        ), 400

    reward = base_reward + (staked_balance * float(profile["stake_bonus_rate"]))
    reward = round(reward, 4)
    if total_supply() + reward > MAX_SUPPLY:
        return jsonify(
            {
                "ok": False,
                "error": f"Supply cap exceeded. Maximum supply is {MAX_SUPPLY:,.0f} BMINI.",
            }
        ), 400

    _, block = issue_consensus_reward(
        wallet=wallet,
        wallet_address=wallet_address,
        reward=reward,
        tx_type="Validated",
        note=f"{profile['label']} validation reward",
        memo="Mobile validator reward",
    )
    wallet["lastValidatedEpoch"] = epoch
    validator_state["validatedCount"] = int(validator_state.get("validatedCount", 0)) + 1
    touch_wallet_activity(wallet)
    maybe_advance_epoch()
    save_state_to_db()

    return jsonify(
        {
            "ok": True,
            "message": "Validation reward added successfully.",
            "reward": reward,
            "consensus": {
                "mode": normalized,
                "label": profile["label"],
                "mobile_ready": profile["mobile_ready"],
                "energy": profile["energy"],
                "epoch": epoch,
            },
            "wallet": {
                "walletAddress": wallet_address,
                "balance": wallet["balance"],
                "stakedBalance": wallet.get("stakedBalance", 0.0),
                "fiatValue": wallet["fiatValue"],
            },
            "block_index": block["index"],
        }
    )


@app.post("/api/register")
def register_wallet():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "New User") or "New User").strip() or "New User"
    username = str(payload.get("username", "") or "").strip()
    email = str(payload.get("email", "") or "").strip()
    date_of_birth = str(payload.get("dateOfBirth", "") or "").strip()
    zip_code = str(payload.get("zipCode", "") or "").strip()
    user_category = normalize_user_category(payload.get("userCategory", "consumer"))
    password = str(payload.get("password", payload.get("passcode", "")) or "").strip()
    referral_code = str(payload.get("referralCode", "") or "").strip()

    normalized_username = normalize_username(username)
    if not name or not normalized_username or not email or not date_of_birth or not zip_code:
        return jsonify({"ok": False, "error": "Name, username, date of birth, zipcode, and email are required."}), 400

    record_wallet_audit_event(
        wallet=None,
        event_type="registration",
        message="Registration attempt received",
        details={"username": normalized_username, "email": email},
    )
    if any(str(existing.get("username", "")).lower() == normalized_username.lower() for existing in wallets.values()):
        return jsonify({"ok": False, "error": "Username is already in use."}), 409

    if len(password) < 8:
        return jsonify({"ok": False, "error": "Password must be at least 8 characters."}), 400

    candidate_unique_id = generate_wallet_unique_id(name, date_of_birth, zip_code, email)
    if any(existing.get("walletUniqueId") == candidate_unique_id for existing in wallets.values()):
        return jsonify({"ok": False, "error": "A wallet already exists for this identity profile."}), 409

    wallet = create_wallet_record(
        name=name,
        username=normalized_username,
        email=email,
        password=password,
        date_of_birth=date_of_birth,
        zip_code=zip_code,
        user_category=user_category,
    )
    referral_bonus = 0.0
    referrer_wallet = get_wallet_by_referral_code(referral_code)
    if referrer_wallet and referrer_wallet.get("walletAddress") != wallet.get("walletAddress"):
        wallet["referredBy"] = referrer_wallet.get("walletAddress")
        wallet["referralActivated"] = False

    network_private_key = decrypt_secret(wallet.get("encryptedPrivateKey", ""), password, wallet.get("authSalt", ""))
    session = create_wallet_session(wallet, network_private_key=network_private_key)
    wallet["failedLoginAttempts"] = 0
    wallet["loginLockedUntil"] = 0
    record_wallet_audit_event(wallet, "registration", "Wallet registration completed", {"walletAddress": wallet.get("walletAddress"), "username": wallet.get("username")}, "info")

    if node_rpc_enabled() and wallet.get("networkPublicKey"):
        node_rpc_request(
            "POST",
            "/rpc/account/create",
            {
                "address": wallet["walletAddress"],
                "public_key": wallet.get("networkPublicKey"),
                "initial_balance": 0.0,
                "locked_balance": 0.0,
            },
        )
    touch_wallet_activity(wallet)

    save_state_to_db()
    wallet_payload = wallet_download_payload(wallet)
    return jsonify(
        {
            "ok": True,
            "message": f"Wallet created for {wallet['name']}.",
            "wallet": wallet_payload,
            "referralBonus": referral_bonus,
            "referralPending": bool(wallet.get("referredBy") and not wallet.get("referralActivated")),
            "sessionToken": session["token"],
            "sessionExpiresAt": session["expiresAt"],
            "downloadUrl": f"/api/wallet/download?address={wallet['walletAddress']}&session={session['token']}",
        }
    )


@app.post("/api/login")
def login_wallet():
    payload = request.get_json(silent=True) or {}
    wallet_address = str(payload.get("walletAddress", "") or "").strip()
    username = normalize_username(payload.get("username", ""))
    method = str(payload.get("method", "password") or "password").strip().lower()
    secret = str(payload.get("secret", "") or "").strip()

    wallet, _ = get_wallet(wallet_address)
    if not wallet and username:
        wallet = next((candidate for candidate in wallets.values() if str(candidate.get("username", "")).lower() == username.lower()), None)
    if not wallet:
        return jsonify({"ok": False, "error": "Wallet not found."}), 404

    lock_active, lock_remaining = wallet_login_lock_status(wallet)
    if lock_active:
        return jsonify({"ok": False, "error": f"Wallet is locked for security reasons. Try again in {lock_remaining} seconds."}), 423

    if method in {"password", "passcode"}:
        expected_hash = wallet.get("passcodeHash")
        auth_salt = wallet.get("authSalt", "")
        if not expected_hash or hash_passcode(secret, auth_salt) != expected_hash:
            attempts = int(wallet.get("failedLoginAttempts", 0) or 0) + 1
            wallet["failedLoginAttempts"] = attempts
            record_wallet_audit_event(wallet, "security", "Failed wallet login attempt", {"method": method, "attempts": attempts}, "warning")
            if attempts >= LOGIN_MAX_ATTEMPTS:
                wallet["loginLockedUntil"] = current_epoch_seconds() + LOGIN_LOCKOUT_SECONDS
                record_wallet_audit_event(wallet, "security", "Wallet login lockout activated", {"attempts": attempts, "lockoutSeconds": LOGIN_LOCKOUT_SECONDS}, "warning")
                save_state_to_db()
                return jsonify({"ok": False, "error": "Wallet is locked for security reasons. Please try again later."}), 423
            save_state_to_db()
            return jsonify({"ok": False, "error": "Invalid password."}), 401
        network_private_key = decrypt_secret(wallet.get("encryptedPrivateKey", ""), secret, auth_salt)
    elif method == "seed_phrase":
        stored_hash = wallet.get("seedPhraseHash")
        if stored_hash:
            if hash_seed_phrase(secret) != stored_hash:
                attempts = int(wallet.get("failedLoginAttempts", 0) or 0) + 1
                wallet["failedLoginAttempts"] = attempts
                record_wallet_audit_event(wallet, "security", "Failed seed phrase login attempt", {"attempts": attempts}, "warning")
                if attempts >= LOGIN_MAX_ATTEMPTS:
                    wallet["loginLockedUntil"] = current_epoch_seconds() + LOGIN_LOCKOUT_SECONDS
                    record_wallet_audit_event(wallet, "security", "Wallet login lockout activated", {"attempts": attempts, "lockoutSeconds": LOGIN_LOCKOUT_SECONDS}, "warning")
                    save_state_to_db()
                    return jsonify({"ok": False, "error": "Wallet is locked for security reasons. Please try again later."}), 423
                save_state_to_db()
                return jsonify({"ok": False, "error": "Invalid seed phrase."}), 401
        elif secret != wallet.get("seedPhrase"):
            attempts = int(wallet.get("failedLoginAttempts", 0) or 0) + 1
            wallet["failedLoginAttempts"] = attempts
            record_wallet_audit_event(wallet, "security", "Failed seed phrase login attempt", {"attempts": attempts}, "warning")
            if attempts >= LOGIN_MAX_ATTEMPTS:
                wallet["loginLockedUntil"] = current_epoch_seconds() + LOGIN_LOCKOUT_SECONDS
                record_wallet_audit_event(wallet, "security", "Wallet login lockout activated", {"attempts": attempts, "lockoutSeconds": LOGIN_LOCKOUT_SECONDS}, "warning")
                save_state_to_db()
                return jsonify({"ok": False, "error": "Wallet is locked for security reasons. Please try again later."}), 423
            save_state_to_db()
            return jsonify({"ok": False, "error": "Invalid seed phrase."}), 401
        network_private_key = None
    else:
        return jsonify({"ok": False, "error": "Unsupported security method."}), 400

    wallet["failedLoginAttempts"] = 0
    wallet["loginLockedUntil"] = 0
    record_wallet_audit_event(wallet, "login", "Wallet login succeeded", {"method": method, "walletAddress": wallet.get("walletAddress")}, "info")
    session = create_wallet_session(wallet, network_private_key=network_private_key)
    sync_active_wallet(wallet)
    touch_wallet_activity(wallet)
    save_state_to_db()
    return jsonify(
        {
            "ok": True,
            "message": "Wallet access granted.",
            "wallet": wallet_download_payload(wallet),
            "sessionToken": session["token"],
            "sessionExpiresAt": session["expiresAt"],
        }
    )


@app.get("/api/health")
def system_health():
    return jsonify(
        {
            "ok": True,
            "status": "ok",
            "network": wallet_state.get("network", "Bitmini Testnet"),
            "phase": DEFAULT_PHASE,
            "chainId": DEFAULT_CHAIN_ID,
            "timestamp": utc_timestamp(),
            "wallets": {
                "total": len(wallets),
                "active24h": sum(1 for wallet in wallets.values() if wallet.get("lastActiveAt") and (current_epoch_seconds() - int(datetime.fromisoformat(str(wallet["lastActiveAt"]).replace("Z", "+00:00")).timestamp()) < 86400)),
            },
            "version": "beta-1.0",
        }
    )


@app.get("/api/admin/audit")
def admin_audit_log():
    wallet, _, auth_error = authorize_admin_request({})
    if auth_error:
        return auth_error

    events = []
    for candidate_wallet in wallets.values():
        for entry in candidate_wallet.get("auditLog", []):
            event = dict(entry)
            event["walletAddress"] = candidate_wallet.get("walletAddress")
            event["walletName"] = candidate_wallet.get("name", "Unknown")
            events.append(event)

    return jsonify({"ok": True, "events": events[:100], "walletAddress": wallet.get("walletAddress")})


@app.post("/api/purchase")
def purchase_bmini():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    if not wallet.get("referralActivated") and not wallet.get("referredBy"):
        return jsonify(
            {
                "ok": False,
                "error": "Real money integrations are not enabled in this deployment. Fiat rails must be configured before this wallet can buy or sell BMINI.",
            }
        ), 400

    usd_amount = float(payload.get("usdAmount", 0) or 0)
    if usd_amount <= 0:
        return jsonify({"ok": False, "error": "Purchase amount must be greater than zero."}), 400

    wallet_state["marketVolumeUsd"] = float(wallet_state.get("marketVolumeUsd", 0.0)) + usd_amount
    wallet_state["price"] = market_price_for_supply()
    unit_price = float(wallet_state.get("price", 0.0) or 0.0)
    if unit_price <= 0:
        unit_price = 0.0001

    token_amount = round_coin(usd_amount / unit_price)
    if token_amount <= 0:
        return jsonify({"ok": False, "error": "Purchase amount too low after conversion."}), 400

    available_minted_supply = max(MAX_SUPPLY - total_supply(), 0.0)
    if token_amount > available_minted_supply:
        return jsonify({
            "ok": False,
            "error": "Users can only buy minted coins. Non-minted supply cannot be purchased.",
        }), 400

    referrer_wallet = None
    if wallet.get("referredBy"):
        referrer_wallet, _ = get_wallet(wallet.get("referredBy"))
    else:
        provided_referral_code = str(payload.get("referralCode", "") or "").strip()
        if provided_referral_code:
            candidate = get_wallet_by_referral_code(provided_referral_code)
            if candidate and candidate.get("walletAddress") != wallet_address:
                wallet["referredBy"] = candidate.get("walletAddress")
                referrer_wallet = candidate

    referral_bonus = 0.0
    referrer_bonus = 0.0
    requested_referral_bonus = 0.0
    referrer_multiplier = 0.0
    mint_total = token_amount
    if referrer_wallet:
        requested_referral_bonus = round(token_amount * REFERRAL_PURCHASE_BONUS_RATE, 4)
        month = current_month_key()
        referral_bonus, referrer_bonus, referrer_multiplier = preview_referral_bonus(
            wallet=wallet,
            referrer_wallet=referrer_wallet,
            amount=requested_referral_bonus,
            month_key=month,
        )
        mint_total += referral_bonus + referrer_bonus

    if not can_mint(mint_total):
        return jsonify({"ok": False, "error": "Purchase exceeds remaining supply cap."}), 400

    credit_wallet(
        wallet=wallet,
        wallet_address=wallet_address,
        amount=token_amount,
        tx_type="Bought",
        note="BMINI purchase",
        memo=f"Purchased ${usd_amount:,.2f}",
    )

    if referrer_wallet and (referral_bonus > 0 or referrer_bonus > 0):
        buyer_granted, referrer_granted, referrer_multiplier = apply_referral_bonus(
            wallet=wallet,
            referrer_wallet=referrer_wallet,
            amount=requested_referral_bonus,
            buyer_memo="Buyer bonus",
            referrer_memo=f"Referred purchase by {wallet_address}",
            note="Purchase referral bonus",
        )
        referral_bonus = buyer_granted
        referrer_bonus = referrer_granted

    touch_wallet_activity(wallet)
    if referrer_wallet:
        touch_wallet_activity(referrer_wallet)

    save_state_to_db()
    return jsonify(
        {
            "ok": True,
            "message": "Purchase completed successfully.",
            "purchase": {
                "usdAmount": usd_amount,
                "tokenAmount": token_amount,
                "referralBonus": referral_bonus,
                "referrerBonus": referrer_bonus,
                "referrerRewardMultiplier": referrer_multiplier,
            },
            "wallet": {
                "walletAddress": wallet_address,
                "balance": wallet["balance"],
                "fiatValue": wallet["fiatValue"],
                "referredBy": wallet.get("referredBy"),
            },
        }
    )


@app.post("/api/sell")
def sell_bmini():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    token_amount = float(payload.get("tokenAmount", 0) or 0)
    if token_amount <= 0:
        return jsonify({"ok": False, "error": "Sell amount must be greater than zero."}), 400

    unlocked_balance = max(float(wallet.get("balance", 0.0)) - float(wallet.get("lockedBalance", 0.0)), 0.0)
    if token_amount > unlocked_balance:
        return jsonify({"ok": False, "error": "Insufficient unlocked balance to sell."}), 400

    current_price = float(wallet_state.get("price", market_price_for_supply()) or market_price_for_supply())
    if current_price <= 0:
        current_price = market_price_for_supply() or 0.0001

    usd_value = round_coin(token_amount * current_price)
    wallet["balance"] = round_coin(float(wallet.get("balance", 0.0)) - token_amount)
    wallet["fiatValue"] = wallet["balance"] * current_price

    sale = {
        "id": f"SALE-{secrets.token_hex(6).upper()}",
        "tokenAmount": round_coin(token_amount),
        "amountUsd": round(usd_value, 2),
        "pricePerCoin": round(current_price, 9),
        "status": "completed",
        "createdAt": utc_timestamp(),
    }
    wallet.setdefault("saleHistory", [])
    wallet["saleHistory"].insert(0, sale)

    tx = {
        "type": "Sold",
        "value": f"-{token_amount:.9f}",
        "amount": f"-${usd_value:,.2f}",
        "note": "BMINI sale",
        "time": "Now",
        "positive": False,
        "recipient": wallet_address,
        "memo": "Sell order completed",
    }
    wallet.setdefault("transactions", [])
    wallet["transactions"].insert(0, tx)

    touch_wallet_activity(wallet)
    save_state_to_db()
    return jsonify(
        {
            "ok": True,
            "message": "Sell order completed successfully.",
            "sale": sale,
            "wallet": {
                "walletAddress": wallet_address,
                "balance": wallet["balance"],
                "fiatValue": wallet["fiatValue"],
            },
        }
    )


@app.post("/api/withdraw")
def request_withdrawal():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    usd_amount = float(payload.get("amountUsd", payload.get("amount", 0) or 0))
    if usd_amount <= 0:
        return jsonify({"ok": False, "error": "Withdrawal amount must be greater than zero."}), 400

    method = str(payload.get("method", "bank") or "bank").strip().lower() or "bank"
    destination = str(payload.get("destination", "Bank account") or "Bank account").strip() or "Bank account"
    available_usd = max(float(wallet.get("fiatValue", 0.0)) - float(wallet.get("lockedBalance", 0.0)) * float(wallet_state.get("price", 0.0) or 0.0), 0.0)
    if usd_amount > available_usd:
        return jsonify({"ok": False, "error": "Withdrawal amount exceeds available USD value."}), 400

    withdrawal = {
        "id": f"WITH-{secrets.token_hex(6).upper()}",
        "amountUsd": round(usd_amount, 2),
        "method": method,
        "destination": destination,
        "status": "pending",
        "createdAt": utc_timestamp(),
    }
    wallet.setdefault("withdrawalRequests", [])
    wallet["withdrawalRequests"].insert(0, withdrawal)

    touch_wallet_activity(wallet)
    save_state_to_db()
    return jsonify({"ok": True, "message": "Withdrawal request created.", "withdrawal": withdrawal})


@app.post("/api/mine")
def mine_transaction():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    profile, normalized = consensus_profile(wallet.get("consensusMode", DEFAULT_CONSENSUS_MODE))
    reward, normalized, profile = effective_reward_for_mode(wallet.get("consensusMode", DEFAULT_CONSENSUS_MODE), payload.get("reward"))
    if reward <= 0:
        return jsonify({"ok": False, "error": "Mining reward must be greater than zero."}), 400

    if total_supply() >= MAX_SUPPLY:
        return jsonify(
            {
                "ok": False,
                "error": "All coins have been minted. Rewards now shift to fee- and stake-based issuance.",
                "issuanceMode": "fee_or_stake",
            }
        ), 400

    if total_supply() + reward > MAX_SUPPLY:
        return jsonify(
            {
                "ok": False,
                "error": f"Mining limit exceeded. Maximum supply is {MAX_SUPPLY:,.0f} BMINI.",
            }
        ), 400

    _, block = issue_consensus_reward(
        wallet=wallet,
        wallet_address=wallet_address,
        reward=reward,
        tx_type="Mined",
        note="Mining reward",
        memo="Successful mining reward",
    )
    touch_wallet_activity(wallet)
    save_state_to_db()

    return jsonify(
        {
            "ok": True,
            "message": "Mining reward added successfully. For mobile devices, use /api/validate with PoS/DPoS/PoA.",
            "reward": reward,
            "consensus": {
                "mode": normalized,
                "label": profile["label"],
                "mobile_ready": profile["mobile_ready"],
                "energy": profile["energy"],
            },
            "wallet": {
                "walletAddress": wallet_address,
                "balance": wallet["balance"],
                "stakedBalance": wallet.get("stakedBalance", 0.0),
                "fiatValue": wallet["fiatValue"],
            },
            "block_index": block["index"],
        }
    )


@app.post("/api/send")
def send_transaction():
    payload = request.get_json(silent=True) or {}
    wallet, wallet_address, auth_error = authorize_wallet_request(payload)
    if auth_error:
        return auth_error

    method = str(payload.get("securityMethod", payload.get("method", "password")) or "password").strip().lower()
    secret = str(payload.get("secret", payload.get("password", payload.get("passcode", ""))) or "").strip()

    if method in {"password", "passcode"}:
        expected_hash = wallet.get("passcodeHash")
        auth_salt = wallet.get("authSalt", "")
        if not expected_hash or not secret or hash_passcode(secret, auth_salt) != expected_hash:
            return jsonify({"ok": False, "error": "Wallet password is required to send money."}), 401
    elif method == "seed_phrase":
        stored_hash = wallet.get("seedPhraseHash")
        if not stored_hash or not secret:
            return jsonify({"ok": False, "error": "Wallet seed phrase is required to send money."}), 401
        if hash_seed_phrase(secret) != stored_hash:
            return jsonify({"ok": False, "error": "Invalid wallet seed phrase."}), 401
    else:
        return jsonify({"ok": False, "error": "Unsupported wallet security method for transfers."}), 400

    amount = float(payload.get("amount", 0) or 0)
    recipient = str(payload.get("recipient", "")).strip()
    memo = str(payload.get("memo", "") or "Transfer").strip() or "Transfer"

    if amount <= 0 or not recipient:
        return jsonify({"ok": False, "error": "Valid recipient and amount are required."}), 400

    if recipient == wallet_address:
        return jsonify({"ok": False, "error": "You cannot send to the same wallet address."}), 400

    duplicate = any(
        tx.get("type") == "Sent"
        and tx.get("recipient") == recipient
        and tx.get("memo") == memo
        and float(str(tx.get("value", "0")).replace("-", "")) == amount
        for tx in wallet.get("transactions", [])
    )
    if duplicate:
        return jsonify({"ok": False, "error": "Duplicate payment detected. This transfer was already sent."}), 400

    session_token = request.headers.get("X-Bitmini-Session") or str(payload.get("sessionToken", "") or "").strip()
    active_session = get_active_session_for_token(wallet, session_token)

    if node_rpc_enabled():
        if not active_session or not active_session.get("networkPrivateKey"):
            return jsonify({"ok": False, "error": "Password login required for network signing."}), 401

        if not wallet.get("networkPublicKey"):
            return jsonify({"ok": False, "error": "Wallet network public key missing."}), 400

        account_status, account_payload = node_rpc_request("GET", f"/rpc/account/{urllib.parse.quote(wallet_address)}")
        if account_status == 404:
            node_rpc_request(
                "POST",
                "/rpc/account/create",
                {
                    "address": wallet_address,
                    "public_key": wallet.get("networkPublicKey"),
                    "initial_balance": float(wallet.get("balance", 0.0)),
                    "locked_balance": float(wallet.get("lockedBalance", 0.0)),
                },
            )
            account_status, account_payload = node_rpc_request("GET", f"/rpc/account/{urllib.parse.quote(wallet_address)}")

        if account_status != 200 or not account_payload.get("ok"):
            return jsonify({"ok": False, "error": account_payload.get("error", "Unable to load node account.")}), 502

        health_status, health_payload = node_rpc_request("GET", "/rpc/health")
        if health_status != 200 or not health_payload.get("ok"):
            return jsonify({"ok": False, "error": health_payload.get("error", "Unable to reach node health endpoint.")}), 502

        account = account_payload.get("account", {})
        tx_payload = {
            "chain_id": health_payload.get("chainId"),
            "sender": wallet_address,
            "recipient": recipient,
            "amount": float(amount),
            "nonce": int(account.get("nonce", 0)) + 1,
            "timestamp": utc_timestamp(),
            "memo": memo,
            "type": "transfer",
        }
        signing_payload = json.dumps(
            {
                "chain_id": tx_payload["chain_id"],
                "sender": tx_payload["sender"],
                "recipient": tx_payload["recipient"],
                "amount": float(tx_payload["amount"]),
                "nonce": int(tx_payload["nonce"]),
                "timestamp": tx_payload["timestamp"],
                "memo": tx_payload.get("memo", ""),
                "type": tx_payload.get("type", "transfer"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        tx_payload["signature"] = ed25519_sign_payload(active_session["networkPrivateKey"], signing_payload)

        submit_status, submit_payload = node_rpc_request("POST", "/rpc/tx/submit", tx_payload)
        if submit_status != 200 or not submit_payload.get("ok"):
            return jsonify({"ok": False, "error": submit_payload.get("message", submit_payload.get("error", "Node rejected transfer."))}), 400

        proposer = health_payload.get("nextProposer")
        node_rpc_request("POST", "/rpc/block/mine", {"proposer": proposer})

        touch_wallet_activity(wallet)
        save_state_to_db()
        return jsonify(
            {
                "ok": True,
                "message": "Transfer submitted to Bitmini network node.",
                "recipient": recipient,
                "amount": amount,
                "node": {
                    "chainId": health_payload.get("chainId"),
                    "nextProposer": proposer,
                },
            }
        )

    amount_usd = wallet_state["price"] * amount
    available_balance = float(wallet.get("balance", 0.0)) - float(wallet.get("lockedBalance", 0.0))
    if amount > available_balance:
        return jsonify({"ok": False, "error": "Insufficient unlocked balance for transfer."}), 400

    wallet["balance"] = max(float(wallet.get("balance", 0.0)) - amount, 0.0)
    wallet["fiatValue"] = wallet["balance"] * wallet_state["price"]

    tx = {
        "type": "Sent",
        "value": f"-{amount:.4f}",
        "amount": f"-${amount_usd:,.2f}",
        "note": f"To {recipient}",
        "time": "Now",
        "positive": False,
        "recipient": recipient,
        "memo": memo,
    }
    wallet.setdefault("transactions", [])
    wallet["transactions"].insert(0, tx)

    activated_bonus = activate_referral_on_first_transfer(wallet)
    if activated_bonus > 0:
        tx["note"] = f"To {recipient} (referral activated)"

    touch_wallet_activity(wallet)
    sync_active_wallet(wallet)
    block = append_block([tx])
    save_state_to_db()

    return jsonify(
        {
            "ok": True,
            "message": "Transfer queued successfully.",
            "recipient": recipient,
            "amount": amount,
            "block_index": block["index"],
            "tx": tx,
        }
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the Bitmini wallet and network app.")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"), help="Host interface to bind to.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Port to listen on.")
    parser.add_argument("--headful", action="store_true", help="Run in browser-friendly development mode with debug and auto-reloader enabled.")
    parser.add_argument("--headless", action="store_true", help="Run in production-style headless mode without debug/reloader.")
    args = parser.parse_args()

    if args.headful and args.headless:
        parser.error("Choose either --headful or --headless, not both.")

    env_mode = os.environ.get("BITMINI_MODE", "").strip().lower()
    if env_mode in {"headful", "headless"}:
        requested_mode = env_mode
    elif args.headful:
        requested_mode = "headful"
    elif args.headless:
        requested_mode = "headless"
    else:
        requested_mode = "headless" if os.environ.get("BITMINI_ENV", "production").lower() == "production" else "headful"

    debug = requested_mode == "headful"
    app.run(host=args.host, port=args.port, debug=debug, use_reloader=debug)
