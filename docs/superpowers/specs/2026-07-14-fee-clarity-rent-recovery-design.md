# Fee Clarity And Rent Recovery Design

## Goal

Make live quote costs understandable before real-money trading and add a manual-only way to recover SOL rent from empty token accounts.

## Safety Boundary

- Only zero-balance token accounts are eligible for rent recovery.
- Token accounts for open live positions are excluded.
- Closing rented accounts is never automatic.
- Every close transaction requires an explicit operator preview and signing step.
- Browser wallet recovery returns an unsigned transaction for wallet approval.
- Local signer paths may submit only through the existing explicit backend submit controls.

## Fee And Spend Clarity

Live buy previews must separate requested trade amount from wallet spend components:

- requested amount
- token-account setup rent
- network/base signature fee
- priority fee
- program fee buffer
- total estimated wallet spend

The UI priority-fee minimum must match the safe dust setting of `0.00001 SOL`, not `0.001 SOL`.

The backend should mark rent-dominant buys when estimated total wallet spend is more than twice the requested buy. Manual review may continue, but autonomous buys should treat that as a blocker.

## Rent Recovery Flow

The backend scans token accounts for the selected wallet through Solana RPC. It reports eligible and ineligible accounts with reasons. A close preview builds a standard SPL Token `CloseAccount` transaction for selected eligible accounts only, sending recovered rent back to the same wallet.

The frontend should surface this in the live wallet workspace as a recovery/review tool, showing recoverable SOL, eligible account count, ineligible reasons, and a preview/sign action.

## Validation

Use tests for:

- rent-dominant spend estimate classification
- priority fee input minimum
- token-account scan eligibility
- exclusion of open live positions
- close transaction preview creation
- API wiring
