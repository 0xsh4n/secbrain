# API Access Controls and BOLA

The most common API security risk is Broken Object Level Authorization (BOLA,
also called IDOR). It maps to the OWASP API Security Top 10 entry API1.

## The problem
An endpoint such as `GET /api/v1/accounts/{account_id}/transactions` must verify
that the authenticated caller is authorized to access the specific
`account_id`. If the server returns data based only on the identifier supplied
by the client, any user can read other users' objects by changing the id.

## Correct enforcement
Perform an object-level authorization check on every request that references an
object by id. Derive the allowed object set from the authenticated principal,
not from client-supplied identifiers. Never rely on the fact that an id is a
UUID or otherwise hard to guess — obscurity is not authorization. Apply the
check in a central policy layer so it cannot be forgotten on new endpoints.
