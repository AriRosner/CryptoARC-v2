# Mobile `image-size` Risk Acceptance

**Decision date:** 2026-08-09  
**Expires:** 2026-11-07T23:59:59Z  
**Tracking:** [GitHub issue #3](https://github.com/AriRosner/CryptoARC-v2/issues/3)

CryptoARC temporarily accepts GHSA-w3rx-r6r6-pgpr and
GHSA-5p2g-fcmc-qvqq for `image-size@1.2.1`. The package is reached through
Expo/Metro asset bundling and is not a mobile runtime dependency. The supported
impact is therefore build-time availability when a crafted asset is processed;
no application, wallet, signer, acknowledgement, arming, or transaction path
imports this package.

The exception is valid only while all of these controls remain true:

- the production audit contains exactly the approved ten-package Metro cascade
  and the two advisory IDs above;
- `image-size` remains locked to 1.2.1 and no compatible patched release exists;
- mobile application source does not import Metro or `image-size`;
- repository mobile assets remain PNG files with valid PNG signatures, plus the
  existing trusted font asset;
- the weekly monitor remains green; and
- the UTC expiry has not passed.

Any additional advisory, severity change, package/path change, unexpected asset
type, invalid image signature, runtime import, tooling failure, upstream release,
or expiration blocks verification. The exception is a review status, not an
audit-zero claim.

## Removal criteria

Remove the exception immediately when a compatible patched release is
available. Update the lockfile without a breaking Expo/React Native downgrade,
rerun the focused exception tests, `scripts/verify-mobile.ps1`, and
`scripts/verify.ps1`, then close issue #3. If no compatible release exists at
expiry, require a new explicit review; do not extend the date automatically.
