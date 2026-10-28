# Password Policy Guidance (Modern, NIST SP 800-63B style)

Modern guidance revises older password rules:

- Favor length over complexity; allow long passphrases (at least 8 characters,
  and support much longer, e.g. 64+).
- Do NOT impose arbitrary composition/complexity rules (forced mix of character
  classes).
- Do NOT force periodic password rotation. Require a change only on evidence of
  compromise. Mandatory periodic expiration is discouraged because it leads to
  weaker, predictable passwords.
- Screen new passwords against breached-password lists.

This directly conflicts with the legacy recommendation of forced 90-day
rotation and mandatory complexity rules.
