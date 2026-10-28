# JWT Validation Best Practices

JSON Web Tokens (JWT) are widely used for authentication. Validating them
correctly is critical to security.

## Verify the signature
Always verify the token signature using the expected algorithm. Reject tokens
whose header specifies `alg: none`. Do not allow the token to dictate the
verification algorithm — pin it server-side to prevent algorithm-confusion
attacks (for example an attacker switching an RS256 token to HS256 and signing
it with the public key as the HMAC secret).

## Validate the claims
Check the `exp` (expiration) and `nbf` (not-before) claims. Validate the `iss`
(issuer) and `aud` (audience) claims against expected values. Reject tokens
that are expired or not yet valid.

## Key management
Use strong keys and rotate signing keys. For RS256, distribute the public key
via a JWKS endpoint and cache it with a sane TTL. Never embed secrets in the
client.
