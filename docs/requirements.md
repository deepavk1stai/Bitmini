# Bitmini MVP requirement mapping

## Product direction

The product brief centers on a mobile-first wallet and payment experience that feels trustworthy to everyday users while still supporting advanced digital currency behavior. The recommended operating model is a staged hybrid custody plan: custodial default for user recovery and support, self-custody opt-in for advanced users, and explicit product boundaries until legal/compliance review is complete.

## MVP scope

### Core app functions

- Create wallet or account
- View balance and fiat equivalent
- Send Bitmini to another address
- Receive Bitmini with QR or address sharing
- Buy and sell through partner integrations
- Track transaction history and confirmations
- Monitor price and alerts
- Maintain contact list and recent recipients
- Show KYC and compliance status
- Provide basic account security controls

### Blockchain and backend expectations

- Native Bitmini transactions
- Node communication and indexing
- Address, balance, and transaction lookups
- Block explorer support
- Admin dashboard and risk checks
- Hybrid custody model with custodial default and optional self-custody support

### Compliance and safety

- KYC / AML checks for buy and sell flows
- Sanctions screening
- Regional controls and support policy
- Strong wallet recovery and backup warnings
- Audit logs and admin access controls

## Recommended MVP implementation priority

1. Hybrid wallet mode with custodial default and self-custody support behind product controls
2. Partner-driven buy / sell flow with KYC and compliance checks
3. Strong price and activity visibility
4. Mobile-first web experience with QR and transfer flows
5. Admin console and blockchain monitoring tools
6. Legal/compliance review before any real-money or transferable-token launch

## Architecture recommendation

- Frontend: responsive web app with wallet dashboard and payment flows
- Backend: accounts, user ledger, order processing, notifications, price feed integration
- Blockchain: node service, transaction broadcaster, explorer, indexer
- Compliance: KYC provider, sanctions scanning, support and audit tooling

## Key product promise

> Create a wallet, buy Bitmini, send it, receive it, sell it, and track it from any mobile browser.
