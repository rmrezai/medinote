# MediNote PHI-Safe Logging Policy

## Principle
Operational observability must not become a secondary clinical data store.

## Permitted
- timestamps
- HTTP status
- service name
- route or route template
- request latency
- internal UUIDs when operationally necessary
- controlled audit event names
- generic exception class/error code

## Prohibited by default
- patient names
- MRNs
- DOBs
- addresses/phone/email
- raw request/response bodies containing clinical content
- imported chart text
- generated or final note text
- medication/diagnosis narrative copied from patient data
- passwords
- bearer/session tokens
- database credentials
- backup passphrases

## Application audit events
Clinical audit events should identify who acted, on which internal object, and when. Metadata should be allow-listed and intentionally non-PHI.

## Proxy/access logs
Do not place patient identifiers in URLs/query strings. Access logs may contain the path and IP address; retention/access must follow organizational policy.

## Debugging
Never enable verbose body logging against real PHI as an ad hoc troubleshooting measure. Reproduce defects with synthetic/de-identified data where possible.
