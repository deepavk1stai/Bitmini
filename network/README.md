# Bitmini Network

This folder contains a standalone Bitmini node for a sovereign network foundation and local test deployment.

## Features
- Own chain ID and genesis file
- 21M supply cap with 1M untouchable genesis reserve
- Local persistent chain/state/mempool/peer storage
- Transaction validation (nonce, Ed25519 signature, balance, lock checks)
- Automatic proposer rotation across validator set
- Validator set governance endpoint (signed governance updates)
- Manual block production endpoint
- Basic peer gossip endpoints for transactions and blocks

## Run

```powershell
py -3 network/bitmini_node.py --host 127.0.0.1 --port 9101 --node-id node-a
```

Start a second node:

```powershell
py -3 network/bitmini_node.py --host 127.0.0.1 --port 9102 --node-id node-b --peer http://127.0.0.1:9101
```

## Core Endpoints
- `GET /rpc/health`
- `GET /rpc/chain/head`
- `GET /rpc/chain`
- `GET /rpc/account/<address>`
- `GET /rpc/token-metrics`
- `POST /rpc/account/create`
- `POST /rpc/tx/submit`
- `POST /rpc/block/mine`
- `POST /rpc/tx/sign` (dev helper)
- `POST /rpc/validators/update`
- `POST /p2p/peers/add`
- `POST /p2p/tx`
- `POST /p2p/block`

## Note
This is a network foundation and local test deployment scaffold. It demonstrates distributed-ledger structure, but it is not yet a production-grade cryptographic network with full hardening, BFT finality, and external-operating security controls.
