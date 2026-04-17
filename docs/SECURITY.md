# Security Model

CryptoARC v2 starts paper-only. Live trading is intentionally deferred until monitoring, scoring, audit logs, and risk controls are stable.

## MVP Rules

- No private keys are accepted.
- No seed phrases are accepted.
- No wallet connection is needed.
- No live transactions are built or sent.
- All trades are simulated.
- Every bot action is explainable in the event log.

## Future Live Rules

- Manual wallet signing is implemented before automated signing.
- Live mode requires explicit confirmation every app start.
- Wallet balance cap is configurable and enforced.
- Daily loss cap is configurable and enforced.
- Trade size cap is configurable and enforced.
- Emergency stop remains available in the primary dashboard.
- Encrypted local hot wallet support, if added, is opt-in and local-only.
