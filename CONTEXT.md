# Wukong ROM Studio

Wukong ROM Studio coordinates private ROM customization jobs across Telegram, cloud runners and the Windows workstation while preserving one shared job history.

## Language

**Telegram User**:
A person identified by an immutable Telegram ID who can open the Mini App and own ROM build jobs.
_Avoid_: Account, chat, customer

**Access Status**:
The current eligibility of a Telegram User: Pending, Approved or Revoked.
_Avoid_: Allowlist entry, enabled flag

**Pending User**:
A known Telegram User whose identity and activity are recorded but who cannot create jobs yet.
_Avoid_: Unknown user, denied user

**Approved User**:
A Telegram User permitted to create jobs while their Build Allowance permits it.
_Avoid_: Whitelisted user

**Revoked User**:
A retained Telegram User whose job creation permission and remaining finite credits have been removed.
_Avoid_: Deleted user, banned row

**Build Allowance**:
The entitlement that permits an Approved User to create jobs, expressed as finite Build Credits or Unlimited access.
_Avoid_: Plan, subscription, monthly quota

**Build Credit**:
One unit of finite Build Allowance consumed when a valid job is accepted and created.
_Avoid_: Token, point

**Accepted Job**:
A validated ROM build request that has received a stable Job ID and entered durable job history.
_Avoid_: Submitted form, attempted build

**Compensation**:
An idempotent restoration of a Build Credit when an Accepted Job could not be durably created or dispatched synchronously.
_Avoid_: Automatic refund for build failure

**Mini App Open**:
One unique client launch session, counted once even when its open request is retried.
_Avoid_: Page view, API request

**Configured Admin**:
A Telegram User declared by deployment configuration who is permanently Approved, Unlimited and non-revocable.
_Avoid_: Superuser row, owner account
