# Bitmini MVP requirement mapping

## Product direction

The product brief centers on a mobile-first wallet and payment experience that feels trustworthy to everyday users while still supporting advanced digital currency behavior.

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
- Self-custody wallets without backend storage of private keys

### Compliance and safety

- KYC / AML checks for buy and sell flows
- Sanctions screening
- Regional controls and support policy
- Strong wallet recovery and backup warnings
- Audit logs and admin access controls

## Recommended MVP implementation priority

1. Custodial wallet mode for general users
2. Self-custody wallet support as a later advanced setting or V1.1 feature
3. Partner-driven buy / sell flow with KYC and compliance checks
4. Strong price and activity visibility
5. Mobile-first web experience with QR and transfer flows
6. Admin console and blockchain monitoring tools

## Architecture recommendation

- Frontend: responsive web app with wallet dashboard and payment flows
- Backend: accounts, user ledger, order processing, notifications, price feed integration
- Blockchain: node service, transaction broadcaster, explorer, indexer
- Compliance: KYC provider, sanctions scanning, support and audit tooling

## Key product promise

> Create a wallet, buy Bitmini, send it, receive it, sell it, and track it from any mobile browser.
