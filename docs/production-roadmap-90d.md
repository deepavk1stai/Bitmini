# Fast-Path Production Roadmap for Bitmini

## Goal

Turn the current prototype into a credible staging testnet without pretending it is production-ready. The decision and legal framing happen first, and the runtime choice is locked before protocol hardening begins.

This is intentionally a fast path: a staged testnet in approximately three weeks, not a 90-day custom-chain production program.

## The central fix

The main contradiction is that the roadmap and testnet plan keep hardening the custom Python chain even though the stack recommendation says not to use it as the production runtime.

The correct approach is:

- decide the runtime in the first 3 days
- keep the Python prototype for economic modeling and product validation
- align the remaining work to the chosen framework
- build a staging testnet under a measured, no-value, no-mainnet claim

## Fast path: about 3 weeks to staging

### Phase 0: Decision and legal framing (Days 1-3)

**Objectives**
- choose the runtime
- establish the decision owner and approval path
- book counsel and an external security reviewer
- define custody, asset-status, jurisdiction, and key-management positioning

**Required outputs**
- signed decision record
- counsel guidance recorded
- runtime spike candidate selected
- project brief showing the chain is not production-ready or mainnet-bound

**Done when**
- the owner, counsel, reviewer, and runtime choice are named in writing
- the decision record is signed by the owner

### Phase 1: Runtime spike and framework short-list (Days 3-8)

**Objectives**
- stand up the chosen framework locally
- validate staking, unbonding, finality, and fee model assumptions
- test validator failure, downtime, and recovery behavior
- decide whether the framework is acceptable or whether another option must be evaluated

**Required outputs**
- 4-validator local devnet
- draft genesis with staking, slashing, and fee configuration
- compare note: framework vs Python prototype
- go/no-go decision on the framework

**Done when**
- one validator can be killed without halting block production
- the devnet still behaves coherently under restart and failure conditions
- the compare note supports a go or no-go recommendation

### Phase 2: Parallel migration and guardrails (Days 3-12)

**Objectives**
- produce a ledger snapshot and reconciliation process
- generate safe genesis allocations from the source ledger
- run the Python economic model to validate rewards and staking assumptions
- define measurable go/no-go gates before testing them

**Required outputs**
- snapshot and reconciliation scripts reviewed before use
- variance report with zero variance before import
- genesis allocation generation procedure and audit trail
- the gate table for soak, partition, backup, double-sign, and migration

**Done when**
- the ledger and balances reconcile cleanly
- the genesis allocation file is reproducible and hash-verified
- go/no-go thresholds are approved before they are tested

### Phase 3: Hardening and staging launch (Days 8-21)

**Objectives**
- secure validator operations
- configure remote signer and separate keys
- add secrets management, monitoring, and runbooks
- run fault drills and rollback rehearsals
- launch a staging network only after gate checks pass

**Required outputs**
- remote signer with double-sign protection
- sentry-node and validator separation model
- monitoring and alerting, with a named on-call
- runbooks for startup, shutdown, incident, upgrade, rollback, and key rotation
- staging testnet ready for operator-driven drills

**Done when**
- the gates pass under test
- findings are recorded and remediated
- the decision owner signs the go/no-go package

## Gate thresholds to fix before measuring

These are the thresholds to apply before the work they measure:

| Gate | Threshold |
| --- | --- |
| Soak | 72 hours at a fixed transaction rate with zero halts and zero invalid blocks accepted |
| Validator failure | Chain recovers within N blocks after a killed proposer |
| Network partition | No conflicting finalized blocks; recovery after partition heals |
| Double-sign protection | Duplicate-key startup is blocked or slashed as configured |
| Backup and restore | Restore within the agreed RTO and match state hashes |
| Migration | Zero variance and second-person reproduction of the genesis hash |
| Admin surface | Start/stop routes disabled or authenticated and logged |
| Secret handling | No validator key in repo or shared host; key ceremony recorded |
| Alerting | Every drill triggers an alert to the on-call person |
| Legal posture | Counsel guidance recorded; public label states no-value testnet |

A failing gate is a no-go, not a note.

## What to keep from the prototype

The repo still provides valuable assets that should carry forward:

- the 7-day testnet runbook as a template for startup, health checks, rollback, and validation
- the risk list for malformed transactions, peer desync, unsafe admin routes, and inconsistent validator sets
- the Python economic model for reward simulation, staking yield, and attack scenarios

## What to avoid

- Do not continue custom protocol hardening on the Python chain without a runtime decision.
- Do not claim production-readiness before gate results are logged and reviewed.
- Do not offer rewards or value claims on testnet until counsel signs off.
- Do not reuse devnet keys outside local devnet usage.
- Do not call any environment production or mainnet-ready until the decision owner signs the archive pack.

## Success criteria

A project is ready for the next stage when:

- runtime choice is recorded and approved
- the staging testnet is stable under failure and recovery
- validator and operator keys are separated and protected
- migration and backup drills pass with zero variance and clean restoration
- legal review and security review have been booked and addressed
- operators and reviewers have complete runbooks and signed go/no-go evidence

This is the compressed path: choose the runtime, harden the deployment, validate a staging network, and do not overclaim before the gates are met.
