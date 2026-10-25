# Validator and Testnet Launch Plan

## Objective
Launch a realistic local validator testnet that demonstrates staking, validator rotation, block production, node health, and operational readiness without claiming production mainnet status.

This plan is the next practical step after the existing local PoS prototype and is designed for a short execution window.

## Phase 0: Scope and constraints
- Goal: run a 3-node validator network locally, then in a staging environment
- Scope: staking, validator selection, block production, node health, peer sync, and launch operations
- Not in scope yet: public mainnet, regulated custody rollout, real-world treasury launch, or broad public launch
- Positioning: devnet/testnet prototype with production-style controls and operational discipline

## Target architecture
### Network layout
- 3 validator nodes
- 1 bootstrap / admin node, optional but useful
- each node runs its own state, mempool, and peer list
- validator set rotates across configured nodes
- each validator publishes health metrics and block height

### Roles
- validator: stakes funds and participates in proposer rotation
- observer: monitors chain health and block data
- operator: handles startup, maintenance, restarts, and incidents
- admin: can trigger devnet launch and status actions through the app

## Requirements
### Runtime requirements
- Python 3.12+
- local host environment or staging VM
- clean data directory per node
- unique ports per node
- reproducible genesis and config files

### Operational requirements
- node startup script
- health endpoint checks
- log collection
- chain status endpoint
- validator status dashboard
- startup/shutdown automation

## Day 1: validator and staking hardening
### Checklist
- finalize staking lock semantics
- add explicit unstaking and payback logic
- add validator eligibility based on stake threshold
- record stake events in ledger and state
- add validator registry and proposal rotation checks
- enforce minimum stake to become active validator

### Deliverables
- validators can stake and unstake through API endpoints
- validator set is visible and reproducible
- next proposer rotates predictably
- invalid stake actions are rejected

## Day 2: signed block production and validator rotation
### Checklist
- confirm block proposer selection matches validator set
- enforce signed block payload validation
- ensure tx validation happens before accepted block creation
- test repeated transactions, invalid signatures, and double-spend conditions
- simulate 3-node block progression for multiple rounds

### Deliverables
- chain produces blocks in multiple rounds
- only the expected proposer can mine the next block
- invalid candidate blocks are rejected
- mempool gets cleared correctly after accepted blocks

## Day 3: peer health and multi-node boot
### Checklist
- start 3 node processes on distinct ports
- add peer URLs for each validator node
- confirm /rpc/health works on every node
- confirm state and peer lists are persisted
- verify block propagation across peers

### Deliverables
- all 3 nodes start successfully
- each node shows correct chain height and next proposer
- peers share transactions and blocks
- node restart does not corrupt state

## Day 4: operator tooling and admin APIs
### Checklist
- add `/api/network/devnet` status endpoint with live running state
- add `/api/network/devnet/start` admin route for devnet startup
- add `/api/network/devnet/stop` route for controlled shutdown
- add validator summary payload
- record active process list and node health metadata

### Deliverables
- operator can start and stop the validator cluster from app/admin API
- health and status are visible in JSON
- devnet state is auditable and easy to debug

## Day 5: validation and rollback testing
### Checklist
- simulate same transaction accepted once
- simulate invalid nonce attempts
- simulate node restart while mempool exists
- simulate block mismatch and reject invalid state_root
- simulate validator removal and rotation edge cases

### Deliverables
- rollback scenarios are understood
- invalid network states are caught cleanly
- validator testnet behaves deterministically under failure

## Day 6: testnet launch rehearsal
### Checklist
- prepare clean environment
- configure node ports and genesis files
- start nodes in sequence
- confirm health endpoints and metrics
- perform a signed tx transfer
- mine a block and verify inclusion
- record status and logs

### Deliverables
- repeatable devnet boot procedure
- single runbook for launch and recovery
- no manual guesswork required during startup

## Day 7: signoff and launch gates
### Go/no-go criteria
- all nodes healthy
- chain height advances without errors
- no invalid blocks accepted
- staking and validator rotation works consistently
- admin controls are tested
- logs are collected and inspectable
- known limitations are written down clearly

### Launch gate checklist
- [ ] nodes start with clean state
- [ ] genesis and keys are generated reproducibly
- [ ] validator set can be enumerated
- [ ] block production improves proposer rotation
- [ ] peer connections remain healthy
- [ ] status endpoints work for ops and monitoring
- [ ] rollback procedure is documented

## Recommended launch pattern
### Stage 1: local devnet
Run a fully local 3-node network with no public exposure.

### Stage 2: staging testnet
Run the same configuration in a cloud or VM environment with a small set of validators.

### Stage 3: public testnet
Only after the staging testnet passes operator and security reviews.

## Suggested operational outputs
- node bootstrap script
- genesis config file
- validator roster file
- health check script
- startup and shutdown runbook
- incident checklist
- release notes for validator/testnet launch

## Risk to watch closely
- malformed transactions
- invalid proposer selection
- peer desynchronization
- unclean state restart after a block is mined
- admin APIs exposing unsafe actions
- inconsistent validator set after governance actions

## Final recommendation
This is the right next milestone because it turns the current prototype into a real, testable validator network without pretending it is mainnet-ready. It gives a credible demonstration of the protocol layer and operational discipline required before any broader public launch.
