# Mobile TLS Certificate Validation and Pinning

Mobile applications must validate TLS server certificates correctly to prevent
man-in-the-middle attacks on untrusted networks.

## Common mistakes
A frequent critical flaw is disabling certificate validation (for example a
custom `TrustManager` that accepts all certificates, or a hostname verifier
that always returns true). This completely breaks transport security.

## Certificate pinning
Certificate pinning restricts which certificates or public keys an app will
accept for a given host, beyond the normal trust store. On Android, the
recommended approach is the Network Security Configuration with `<pin-set>`
entries. On iOS, pinning can be implemented via `URLSession` delegate methods
or App Transport Security. Pin to the public key (SPKI) rather than the leaf
certificate so rotation does not break the app, and always configure a backup
pin to avoid locking users out when a key is rotated.
