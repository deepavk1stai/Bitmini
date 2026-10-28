# Production Stack Recommendation for Bitmini

## Decision

This repo is a strong prototype and a credible product foundation, but the stack recommendation is now explicit: do not treat the custom Python chain as the canonical production runtime unless the team is intentionally accepting a large protocol, security, and operations burden.

The recommended decision path is:

- Keep the product concepts, wallet app, and economic simulation work.
- Use a framework-backed chain runtime for validator staking and chain operations.
- Use the Python prototype only as a product and economics lab, not as the production consensus runtime.

## Recommendation

Choose the runtime based on what the product needs most:

- Cosmos SDK + CometBFT if validator-staked PoS and chain-level governance are central
- Substrate / Polkadot SDK if custom runtime logic and maximum chain flexibility are the priority
- EVM-compatible stack if wallet compatibility and developer tooling matter more than owning a custom validator set

This is the central decision. Until it is made, roadmap work that hardens the custom Python chain is likely throwaway work.

## Why the custom Python chain is not the production default

A custom blockchain runtime requires:

- consensus engineering
- peer discovery, gossip, and sync logic
- transaction validation and fee logic
- key management and cryptographic discipline
- remote signing and validator security controls
- validator slashing, unbonding, and governance logic
- operational hardening, backup, and recovery
- legal and compliance framing

This is substantially beyond a prototype. It creates a large audit surface, and it is not the fastest route to a credible staging testnet.

## Decision matrix

| Criterion | Keep Python chain | Cosmos SDK + CometBFT | Substrate / Polkadot SDK | EVM chain / L2 |
| --- | --- | --- | --- | --- |
| Time to credible testnet | Slow | Fast | Medium | Fast |
| Staking, slashing, governance built in | No | Yes | Yes | Depends |
| Team fit | Python | Go | Rust | Solidity + tooling |
| Wallet and explorer ecosystem | Limited | Good | Good | Best |
| Customization | Total | High | Highest | Contract-level |
| Audit surface you own | Entire protocol | Your modules only | Your pallets/runtime | Your contracts |
| Fit with validator economics | Weak | Strong | Strong | Weak unless you own the chain |

## Recommended execution model

1. Keep the Bitmini wallet app, app UX, staking concepts, and value-flow model.
2. Choose one framework by day 3 and freeze the decision in writing.
3. Run a local runtime spike on the chosen framework with at least 4 validators.
4. Keep the Python prototype for simulation, economic modeling, and migrations.
5. Treat the repo as an app and product layer around the final chain runtime, not as the final runtime itself.

## Proposed architecture

- Application layer: Bitmini wallet UI, admin API, onboarding, staking dashboard
- Chain runtime: Cosmos SDK or Substrate runtime
- Validation layer: framework-native validator network
- Security layer: remote signer, double-sign protection, secrets management, audit logging
- Operations layer: monitoring, alerts, CI/CD, restore drills, and rollback

## Important production constraints

- The chain must not claim production status before a staging or testnet review passes.
- Testnet tokens must be labeled as having no value and must not be offered as an incentive until legal review signs off.
- The finality model, validator set policy, custody model, and sanctions posture must be recorded before launch.
- Devnet keys must never be reused in staging or production-like environments.

## Bottom line

If the objective is a credible, operationally safe launch path, choose a proven blockchain framework and use the current repo as a prototype, simulation environment, and migration pipeline. The custom Python chain is a good product prototype, but it should not be the default production runtime.
