# Bitmini Production Readiness Checklist

This checklist defines the gaps between the current local PoS prototype and a production-ready blockchain product.

## 1. Protocol and consensus
- [ ] Real validator onboarding and offboarding
- [ ] Stake lock, unlock, and unbonding rules with clear timing
- [ ] Slashing conditions and penalty enforcement
- [ ] Finality and fork selection rules
- [ ] Signed block validation
- [ ] Reorg handling and state rollback paths
- [ ] Replay protection across validators and nodes
- [ ] Mempool fairness and spam protection
- [ ] Network synchronization and peer consensus checks

## 2. P2P networking
- [ ] Authenticated peer discovery
- [ ] Peer gossip for transactions and blocks
- [ ] Sync from multiple peers and peer health checks
- [ ] NAT traversal / public node support
- [ ] Partition recovery and long-range sync
- [ ] Node status, metrics, and telemetry
- [ ] Metrics for peer churn, latency, and block propagation

## 3. Security and key management
- [ ] Separate validator keys from wallet keys
- [ ] Secure private key storage
- [ ] Key rotation and backup procedures
- [ ] Secrets management (Vault / cloud KMS / HSM-backed solution)
- [ ] No secrets in repo, configs, logs, or crash reports
- [ ] Authentication hardening for admin APIs
- [ ] Rate limiting and abuse protection
- [ ] Endpoint authorization review
- [ ] Dependency vulnerability scanning
- [ ] Static analysis and security linting
- [ ] Threat model and incident response plan

## 4. State durability and recovery
- [ ] Crash-safe chain storage
- [ ] State migrations and schema versioning
- [ ] Backup/restore procedures
- [ ] Replay and recovery plan
- [ ] Historical state validation
- [ ] Audit log retention policy

## 5. Deployment and operations
- [ ] Staging environment
- [ ] Production environment segmentation
- [ ] CI/CD with protected deployments
- [ ] Automated rollback procedure
- [ ] Monitoring and alerts
- [ ] SLOs for uptime and block production
- [ ] Runbooks for validator issues and disputes
- [ ] Capacity planning and scaling plan

## 6. Economics and governance
- [ ] Emission rules and treasury controls
- [ ] Reward policy documentation
- [ ] Slashing policy documentation
- [ ] Governance or emergency pause mechanism
- [ ] Upgrade path and network freeze policy
- [ ] Reserve and treasury management

## 7. Compliance and legal
- [ ] KYC/AML flow for onboarding and validator participation
- [ ] Sanctions screening
- [ ] Wallet recovery and user protection controls
- [ ] Terms of service and privacy policy
- [ ] Custody disclosures
- [ ] Audit and compliance logging
- [ ] Jurisdiction mapping for wallet and validator operations

## 8. Product readiness
- [ ] Wallet recovery flow
- [ ] Secure seed phrase backup and restore
- [ ] Multi-device session handling
- [ ] Fraud detection and suspicious activity controls
- [ ] Admin tooling and customer support workflows
- [ ] Documentation for validator operators and users

## 9. Audit and verification
- [ ] Third-party security review
- [ ] Code review and formal verification review for critical logic
- [ ] Fuzz testing and adversarial tests
- [ ] Pre-production testnet with real validator simulation
- [ ] Emergency patching and release policy

## 10. Current status of this repo
This repo is a strong local PoS prototype, but it is not yet a production-ready blockchain. It requires a second-phase transition from prototype consensus to hardened network operations, secure infrastructure, and legal/compliance controls.
