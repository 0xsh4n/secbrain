# Authentication vs Authorization

Authentication and authorization are distinct controls that are often confused.

## Authentication (AuthN)
Authentication answers "who are you?". It is the process of verifying the
identity of a user or service — for example by checking a password, a hardware
token, a client certificate, or a federated identity assertion. Successful
authentication establishes a verified principal.

## Authorization (AuthZ)
Authorization answers "what are you allowed to do?". It is the process of
deciding whether an already-authenticated principal may perform a specific
action on a specific resource. Role-based access control (RBAC) and
attribute-based access control (ABAC) are common authorization models.

## Why the distinction matters
A system can authenticate a user correctly but still fail authorization by
granting excessive privileges. Broken access control (authorization failure)
is consistently among the most common and impactful web vulnerabilities.
Authentication happens first; authorization is enforced on every request.
