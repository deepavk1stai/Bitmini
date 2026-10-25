# Legal-ready launch boundaries and deployment checklist

## Operating model

Bitmini should launch as a staged hybrid custody product, not as a fully self-custody or unregulated payment app.

- Default custody model: custodial support and recovery for general users.
- Optional advanced path: self-custody opt-in behind explicit user warnings and product controls.
- Real-money flows: disabled until a licensed payment provider, legal review, and policy controls are operational.
- Public wallet access: beta-only until KYC, sanctions screening, and admin governance are verified.

## Launch gates before any live rollout

1. KYC / AML / sanctions screening is active for all wallet onboarding and payment flows.
2. Admin governance review is required for wallet approvals, overrides, and payout actions.
3. Ledger and persistence layers use encrypted, WAL-backed SQLite storage and integrity checks.
4. Manual review is required for withdrawals, high-risk countries, and suspicious risk patterns.
5. Product copy and UI clearly state the hybrid custody model and beta status.
6. Regional restrictions and sanctions review are integrated before any public transfer or fiat flow is enabled.

## Deployment checklist

- Confirm legal entity, jurisdiction, and operating model.
- Add KYC provider and sanctions screening integration.
- Configure admin governance role separation and approval logs.
- Enable encrypted SQLite storage, WAL mode, and integrity verification.
- Disable real-money rails until provider and compliance controls are live.
- Document user warnings for custodial default, backup, and self-custody opt-in wording.
- Review terms, disclosures, user communications, and incident response procedures.
- Validate that all launch readiness checks pass through the admin governance endpoints.

## Hard boundaries

- No unreviewed public market launch.
- No live fiat funding or cash-out before legal and operational controls are in place.
- No self-custody claim without explicit user consent, recovery education, and risk warnings.
- No admin override without audit logging and approval evidence.
