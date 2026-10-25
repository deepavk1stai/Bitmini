# 90-Day Production Roadmap from the Current PoS Prototype

## Goal
Turn the current local PoS prototype into a production-grade blockchain foundation that is operationally safe, compliant, and deployable in a real testnet with production-grade engineering discipline.

## Phase 1: Stabilize the protocol foundation (Days 1-15)
### Deliverables
- finalize staking semantics and lock periods
- validate validator registry and proposer rotation logic
- document consensus invariants and failure modes
- harden tx validation and rejection of malformed data
- add state migration and durable storage practices

### Tasks
- lock stake and unlock flows
- build validator onboarding/offboarding rules
- define slashing and reward accounting model
- add deterministic validator selection logic
- expand chain state tests to include edge cases and corruption recovery
- improve database persistence and crash safety

## Phase 2: Network readiness (Days 16-35)
### Deliverables
- hardened p2p node communication
- peer discovery and health monitoring
- block propagation and sync logic
- node status metrics and dashboards
- multi-node testnet deployment plan

### Tasks
- build real peer discovery and registry
- add block gossip and transaction broadcast
- implement sync rules for new and lagging nodes
- add node uptime, block height, and validator health metrics
- run a 3-10 node testnet with validator rotation and rewards

## Phase 3: Security and ops hardening (Days 36-55)
### Deliverables
- secure secret management
- protected admin API and role separation
- CI/CD pipeline and deployment controls
- alerting, monitoring, runbooks
- security scanning and dependency review

### Tasks
- separate wallet keys and validator keys
- move secrets into secure storage
- add audit logging, rate limits, and abuse defenses
- implement testing and release gates
- create runbooks and incident escalation flow
- add deployment environment separation (dev, staging, prod)

## Phase 4: Compliance and legal readiness (Days 56-75)
### Deliverables
- KYC/AML model
- sanctions screening design
- compliance controls
- user recovery and custody disclosure plan
- governance policy and risk documentation

### Tasks
- define identity and risk tiers
- document wallet custody model and disclosures
- map compliance requirements for each operating region
- add risk review flows for wallets and validators
- finalize launch controls and legal review gates

## Phase 5: Production launch simulation (Days 76-90)
### Deliverables
- production-style testnet launch
- validator onboarding package
- incident drill and rollback drill
- final readiness review
- go/no-go decision framework

### Tasks
- launch a testnet with real operators and validators
- simulate outages, reorgs, and slashing events
- perform disaster recovery simulation
- audit docs, keys, procedures, and ownership
- produce launch checklist and production signoff pack

## Recommended strategy
The best path is not to keep making the custom Python chain the production chain. Instead:
- keep the product and wallet concepts
- use a proven blockchain framework for the network runtime
- keep your repo as the app and product layer around the chain runtime
- use the prototype for product validation and economic design

## Success criteria
A project is ready to move toward production when:
- consensus is proven under failure conditions
- node coordination works across multiple validators
- key management is secure
- ops and monitoring are in place
- legal/compliance controls are defined
- testnet launch and rollback drills pass
