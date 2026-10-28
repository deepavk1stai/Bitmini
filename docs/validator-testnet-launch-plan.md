# Validator and Testnet Launch Plan

## Objective

Launch a realistic validator testnet that demonstrates staking, validator rotation, block production, node health, and operational readiness without claiming production or mainnet status.

This plan is the next practical step after the local PoS prototype and should be executed with a framework decision already made and a written legal posture in place.

## Critical fix from the review

A 3-node BFT network cannot tolerate a single failure. BFT-style consensus requires 3f+1 validators to survive f faults. With 3 validators, losing one leaves the network below a supermajority and the chain can halt.

Therefore:

- use at least 4 validators for the minimum local testnet
- use 7 validators if the goal is a realistic failure drill
- test one node down, a second node down, and a partitioned validator cluster explicitly

## Phase 0: scope and constraints

- Goal: run a validator network locally and then in a staging environment
- Scope: staking, validator selection, block production, node health, peer sync, faults, and ops
- Constraints: no mainnet claim, no value claim on testnet tokens, no casual reuse of devnet keys
- Positioning: devnet/testnet prototype with production-style controls and operational discipline

## Target architecture

### Network layout

- 4 validator nodes minimum (7 recommended)
- 1 optional bootstrap or admin node
- each node has its own state, mempool, and peer list
- validator set rotates among configured validators
- each validator publishes health metrics and block height

### Roles

- Decision owner: approves runtime, custody, legal posture, and go/no-go
- Protocol engineer: owns genesis, staking, slashing, fee model, and chain configuration
- Application engineer: wallet signing, explorer, indexer, admin API integration
- Data and migration engineer: snapshot, reconciliation, genesis export, audit pack
- Security and key custodian: remote signer, key separation, key ceremony, secrets management
- Operations engineer: monitoring, alerts, CI/CD, runbooks, drills
- Counsel: reviews token and incentives posture
- External reviewer: security and economic review

## Requirements

### Runtime requirements

- Python 3.12+
- local host or staging VM
- clean data directory per node
- unique ports per node
- deterministic genesis and config generation

### Operational requirements

- startup script
- health endpoint checks
- log collection and node status export
- status endpoints for validator health
- runbooks for startup, shutdown, rollback, and key rotation
- remote signer or HSM-backed signing path for validators

## Decision record template to enforce before work begins

Record the following before the devnet test begins:

| Decision | Options | Recommended default | Reason |
| --- | --- | --- | --- |
| Runtime | Python chain, Cosmos SDK, Substrate, EVM | Cosmos SDK, pending the spike | Staking, slashing, and validator sets are built in |
| Custody model | Custodial, self-custody, hybrid | Hybrid | Avoids false self-custody claims |
| Asset status | Transferable token, in-app credit | In-app credit on testnet | No value claims before counsel review |
| Validator set at launch | Permissioned, open | Permissioned | Lower risk while parameters are unproven |
| Finality | Instant BFT, probabilistic | Instant BFT | Clear expectations for test and rollback |
| Testnet incentives | None, points, tokens | None | Avoid legal and expectation risk |
| Jurisdictions | list of regions | Counsel to advise | Drives compliance scope |
| Key management | Local keys, remote signer, HSM | Remote signer with double-sign protection | Prevents accidental slashing |

## Day 1: validator and staking hardening

### Checklist

- finalize staking lock semantics
- add explicit unstaking and payback logic
- add validator eligibility based on stake threshold
- record stake events in the ledger and state
- add validator registry and proposer-rotation checks
- enforce minimum stake for active-validator status
- define slashing parameters and unbonding period

### Deliverables

- validators can stake and unstake through API endpoints
- active validator set is visible and reproducible
- next proposer rotates predictably
- invalid stake actions are rejected

## Day 2: signed block production and validator rotation

### Checklist

- confirm proposer selection matches the validator set
- enforce signed block payload validation
- ensure transaction validation happens before block acceptance
- test repeated transactions, invalid signatures, and double-spend conditions
- simulate multi-round block progression on a 4-node devnet

### Deliverables

- the chain produces blocks in multiple rounds
- only the expected proposer can mine the next block
- invalid candidate blocks are rejected
- mempool is cleared correctly after inclusion

## Day 3: peer health and multi-node boot

### Checklist

- start 4 validator processes on unique ports
- configure peer URLs for all validator nodes
- confirm `/rpc/health` works on every node
- confirm state and peer lists persist across restarts
- verify block propagation and peer sync behavior

### Deliverables

- all nodes start successfully
- each node shows correct chain height and next proposer
- peers share transactions and blocks
- restart does not corrupt state

## Day 4: operator tooling and admin APIs

### Checklist

- add `/api/network/devnet` status endpoint with live state
- add `/api/network/devnet/start` admin route for devnet startup
- add `/api/network/devnet/stop` route for controlled shutdown
- add a validator summary payload
- record active process list and health metadata
- ensure admin endpoints are authenticated and logged

### Deliverables

- operator can start and stop the cluster from the app or admin API
- chain health is visible in JSON
- the devnet is auditable and easy to debug

## Day 5: validation, rollback, and fault testing

### Checklist

- simulate the same transaction being accepted once
- simulate invalid nonce attempts
- simulate node restart while the mempool still has transactions
- simulate block mismatch and reject invalid `state_root`
- simulate validator removal and rotation edge cases
- test a killed proposer and a second failed validator

### Deliverables

- rollback scenarios are understood
- invalid network states are caught cleanly
- the validator testnet behaves deterministically under failure

## Day 6: testnet launch rehearsal

### Checklist

- prepare a clean environment
- configure node ports and genesis files
- start nodes in sequence
- confirm health endpoints and metrics
- perform a signed transfer
- mine a block and verify inclusion
- record logs and artifacts for the review

### Deliverables

- repeatable devnet boot procedure
- single runbook for launch, recovery, and rollback
- zero manual ambiguity during startup

## Day 7: signoff and launch gates

### Go/no-go criteria

- all nodes are healthy
- block height advances without errors
- no invalid blocks are accepted
- staking, slashing, and validator rotation work consistently
- admin controls are tested and protected
- logs are collected and inspectable
- known limitations are written down clearly

### Launch gate checklist

- [ ] all nodes start with clean state
- [ ] genesis and keys are generated reproducibly
- [ ] validator set can be enumerated
- [ ] proposer rotation remains consistent under load
- [ ] peer connections remain healthy
- [ ] status endpoints work for ops and monitoring
- [ ] rollback procedure is documented
- [ ] key ceremony and access control are logged

## Recommended launch pattern

### Stage 1: local devnet

Run a fully local validator network with no public exposure.

### Stage 2: staging testnet

Run the same configuration in a cloud or VM environment with a small set of validators.

### Stage 3: public testnet

Only after the staging network passes operator, security, and counsel review.

## Runtime spike test plan

Use the framework’s own scaffold and standard modules before writing custom code. Run every test on the 4-validator local devnet and record the result in a shared log with the date, node version, and commands used.

| # | Test | How to run it | Pass criterion |
| --- | --- | --- | --- |
| 1 | Clean boot | Start 4 validators | All nodes begin and join the same chain |
| 2 | Staking and unbonding | Stake, unstake, and wait through unbonding | Balances and validator power change exactly as configured |
| 3 | One validator down | Stop one validator process | Block production continues without a halt |
| 4 | Two validators down | Stop a second validator | Chain halts and resumes cleanly when a node returns |
| 5 | Double-sign attempt | Start a second instance with the same validator key on a throwaway devnet | The validator is jailed or slashed per configuration |
| 6 | Replay protection | Submit a signed transaction with a different chain ID | Transaction is rejected |
| 7 | Spam control | Send transactions at zero or minimal fee | Transaction is rejected or priced per the fee model |
| 8 | Restart with mempool | Kill and restart a node with pending transactions | State is intact; no duplicate execution |
| 9 | State recovery | Wipe one node and rejoin via sync | The node reaches current height and matches others' state hash |

## Operational gates

These are the precise operational thresholds to hold before the day-21 review:

| Gate | Proposed threshold | Evidence to keep |
| --- | --- | --- |
| Soak | 72 hours at a fixed transaction rate with zero halts and zero invalid blocks accepted | block height log and node health export |
| Validator failure | Chain recovers within N blocks after a killed proposer | timestamped drill log |
| Network partition | No conflicting finalized blocks; chain resumes after the partition heals | state hash comparison across nodes |
| Double-sign protection | Duplicate-key startup is blocked by the remote signer or slashed as configured | test log from spike and staging repeat |
| Backup and restore | A node restored from backup rejoins within the RTO and matches state hashes | restore log and hash output |
| Migration | Zero variance and a second person reproduces the genesis hash | audit pack |
| Admin surface | Process start/stop routes are disabled or authenticated and logged in staging | config diff and access test |
| Secrets and keys | No validator key in repository or on a shared host; key ceremony recorded | scan report and ceremony record |
| Alerting | Each drill triggers an alert that reaches the on-call person | screenshot/log per drill |
| Legal posture | Counsel guidance recorded; testnet labeled as having no value | written guidance and header label |

## Drills and operations checklist

Run each drill with real operators, not only the engineer who built the setup.

| Drill | Scenario | Success criterion |
| --- | --- | --- |
| Validator outage | Stop one validator and restore it | Alert fires, runbook is followed, chain never halts |
| Failover without double-sign | Move a validator to standby | Old instance is confirmed stopped first; no slashing event |
| Bad block or state mismatch | Feed invalid block or mismatched state root | Node rejects it and the operator can identify the cause |
| Network partition | Split validators into groups and reconnect | No safety violation; recovery matches runbook |
| Node data loss | Wipe one node and restore it | Rejoins within RTO and matches state hashes |
| Coordinated upgrade | Apply a software upgrade across all validators | Nodes agree on upgrade height with no split |
| Rollback | Revert after failed upgrade | Documented rollback sequence works end-to-end |
| Key incident | Treat one operator key as exposed and rotate it | Rotation completes without halting the chain |

## Checklist before the review

- Runbooks exist for startup, shutdown, incident, upgrade, rollback, and key rotation, and each was used in a drill.
- Monitoring covers block height, validator uptime, peer count, mempool size, disk, and signing health, with alerts routed to a named on-call person.
- Dev, staging, and production-like environments are separated, with separate keys and secrets.
- CI/CD builds are reproducible and gated by tests; releases require approval.
- Dependency and secret scans have no open critical findings.
- Known limitations are written down and shared with every operator.

When the checklist and gate table are complete, the decision owner signs the go/no-go and the audit pack is archived.
