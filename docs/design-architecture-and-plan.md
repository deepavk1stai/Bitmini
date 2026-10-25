# Bitmini Design, Architecture, and Implementation Plan

## 1. Product overview
Bitmini is a wallet-first digital value and rewards platform built around:
- hybrid custody architecture with custodial default and self-custody opt-in
- referral-based incentives
- validator and stakeholder participation
- ad-driven monetization and engagement
- future fiat conversion marketplace under legal/compliance review

The current version is a beta-ready foundation for a mobile-friendly consumer app and network economy.

## 2. Product goals
- Create a simple wallet experience that works from a phone.
- Give users a way to earn and receive value through wallet actions, validation, referrals, and ads.
- Protect all wallet operations with authentication and audit logging.
- Build a network economy that can support sustainable growth before direct fiat conversion is added.
- Plan for a future exchange layer without exposing premature unsupported claims.

## 3. User roles
### Consumer
- Holds BMINI in wallet
- Sends money to other wallets
- Uses wallet for payments and transfers
- Participates in rewards and promotions

### Validator
- Stakes or participates in consensus
- Helps secure or validate the network
- Earns rewards for honest validator behavior

### Promoter
- Creates promotional campaigns
- Purchases ad budgets
- Pays wallet users to view or interact with content

### Advertiser
- Funds ad campaigns
- Sets ad spend strategies and priorities
- Drives network demand and wallet activity

## 4. Business model
### Core value drivers
- wallet usage
- network participation
- referral onboarding
- ad spend demand
- validator involvement

### Reward logic
- Users earn through referrals, validation, and ad-view participation.
- Referral rewards are progressive rather than arbitrarily capped at a tiny threshold.
- Ad sellers spend BMINI budgets to purchase views and exposure.

## 5. Architecture
### Backend
- Python + Flask application in app.py
- SQLite for persistent state storage in the beta prototype
- Session-based authorization for wallet actions
- Encrypted wallet state and transaction history storage
- Hybrid custody design that separates custodial support flows from self-custody opt-in paths

### Frontend
- Flask templates for public pages and wallet shell
- Static JS/CSS for interactive homepage and wallet UI behavior

### State model
- wallet_state holds global system configuration
- wallets holds each user wallet record including balance, role, auth, and activity
- ledger stores canonical transaction history
- validator_state tracks network validation state

## 6. Core modules
### Wallet module
Responsibilities:
- wallet registration
- wallet login with password or seed phrase
- wallet session creation and validation
- self-custody wallet management
- balance tracking and transaction history

### Security module
Responsibilities:
- password hashing
- seed phrase verification
- failed-login lockout tracking
- audit events
- admin access guard

### Referral module
Responsibilities:
- wallet referral codes
- inviter/invitee tracking
- monthly reward caps and progressive multipliers
- referral leaderboard data
- activation bonus logic

### Ad module
Responsibilities:
- ad creation and pricing
- creation by allowed seller categories only
- ad ranking by spend-per-view and priority
- one-view-per-wallet prevention
- ad payout and budget tracking

### Validation module
Responsibilities:
- staking and validation logic
- consensus mode variation
- reward distribution to validators and participants

### Market/pricing module
Responsibilities:
- compute price based on activity and supply
- value estimation in USD terms
- purchase/sell logic and future market integration

## 7. Data structures
### Wallet record fields
- name
- username
- email
- dateOfBirth
- zipCode
- walletAddress
- walletUniqueId
- referralCode
- referredBy
- referralEarnings
- referralActivated
- authSalt
- passcodeHash
- seedPhraseHash
- userCategory
- userCategories
- securityMethods
- sessions
- auditLog
- failedLoginAttempts
- loginLockedUntil
- balance
- lockedBalance
- price
- fiatValue
- transactions
- alerts
- contacts

### Ledger transaction fields
- type
- value
- amount
- note
- memo
- timestamp
- recipient
- sender

### Ad fields
- id
- sellerWalletAddress
- adType
- title
- description
- mediaUrl
- targetUrl
- bidPerView
- budgetTotal
- budgetRemaining
- status
- viewCount
- viewers
- totalSpent
- createdAt
- updatedAt

## 8. Security model
- Wallet actions require session validation before sensitive writes.
- Sending funds requires the user to authenticate through password or seed phrase.
- Repeated invalid login attempts trigger temporary lockout.
- Audit entries are stored on each wallet for traceability.
- Admin endpoints are restricted to admin-role wallets.

## 9. User flow design
### Registration flow
1. User fills name, username, DOB, zip code, email, password.
2. App validates identity fields and uniqueness.
3. System creates wallet and referral code.
4. Wallet is saved and session created.
5. User is redirected to wallet app.

### Login flow
1. User provides wallet address or username.
2. User selects password or seed phrase mode.
3. Secret is validated.
4. On success, session token is created and app unlocks wallet.
5. On repeated failure, lockout triggers.

### Send flow
1. User is authenticated.
2. Must re-enter correct password or seed phrase.
3. Transaction is validated.
4. Ledger and wallet balances are updated.

### Ad flow
1. Seller must have promoter or advertiser category.
2. Seller creates ad listing with bid and budget.
3. Budget is reserved from wallet balance.
4. Ads are ranked by highest spend-per-view priorities.
5. Viewers receive reward and can only claim a given ad once.

## 10. Future fiat conversion design
This is the next layer beyond beta.

### Future features
- seller lists BMINI at fiat price
- buyer sees ask/bid offers
- escrow and matching engine
- fiat settlement to bank/card/wallet networks
- compliance logic and user verification

### Suggested architecture
- Market API layer for buy/sell orders
- Wallet settlement engine
- Payout ledger for fiat-backed trades
- Admin compliance review

### Important rule
The project should not claim direct fiat conversion until a real payment and settlement system is connected.

## 11. Implementation priorities
### Phase 1: Beta hardening
- lockout and audit behavior
- secure send auth
- health/admin diagnostics
- clean wallet login flow
- final UX consistency

### Phase 2: Growth economy
- referral analytics dashboard
- top earners and leaderboard improvements
- ad ranking and spend analytics
- mobile UX refinement

### Phase 3: Exchange readiness
- seller fiat market listing and matching engine
- fiat payment rails
- automated compliance and settlement
- liquidity management

### Phase 4: Production hardening
- legal pages
- env config cleanup
- monitoring and backup planning
- abuse controls and anti-fraud checks

## 12. Risks and safeguards
- referral abuse by repeated low-quality invites
- ad spam and repeated viewing
- wallet access compromise
- fake or manipulated market value claims
- misrepresentation of fiat conversion capability

### Control measures
- progressive referral rewards
- anti-spam ad view rules
- session-bound wallet auth
- role-based management access
- clearly labelled future-market features

## 13. Current status
The codebase currently implements the foundational beta features:
- wallet auth and access control
- referral rewards and leaderboards
- ad marketplace logic
- top earners and transaction homepage blocks
- beta-level monitoring and audit protection

This makes the app viable as a working beta or early prototype for wallet-first digital value and rewards while keeping direct fiat conversion as a future milestone.

## 14. Final recommendation
Proceed with the app as a beta-worthy wallet/reward/ad platform, while explicitly labeling fiat conversion as a future phase. This avoids making unsupported claims while still delivering a strong product foundation.
