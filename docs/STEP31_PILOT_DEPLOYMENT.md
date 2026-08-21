# MediNote Step 31 - Pilot Deployment Package v0.1

## Purpose
This package prepares MediNote for a controlled small-hospitalist-group pilot deployment. It is an engineering deployment baseline, not a representation of HIPAA certification, regulatory clearance, or production authorization for PHI without institutional security/privacy review.

## Deployment topology

Internet / hospital workstation
  -> HTTPS 443
  -> Caddy reverse proxy
      -> frontend (internal HTTP)
      -> API (internal HTTP)
          -> PostgreSQL (internal network only)

Only ports 80/443 are published by the pilot compose file. PostgreSQL and the API are not directly exposed to the host network.

## Files
- `docker-compose.pilot.yml` - pilot deployment stack
- `.env.pilot.example` - required environment/secrets template
- `deploy/caddy/Caddyfile` - TLS/reverse proxy/security headers
- `deploy/scripts/preflight.sh` - refuses placeholder secrets and checks prerequisites
- `deploy/scripts/deploy.sh` - one-command deployment
- `deploy/scripts/status.sh` - service status
- `deploy/scripts/backup.sh` - encrypted PostgreSQL backup
- `deploy/scripts/restore.sh` - encrypted backup restore

## Host prerequisites
- Linux server/VM under organization control
- Docker Engine + Docker Compose v2
- DNS A/AAAA record for the MediNote hostname pointing to the server
- inbound TCP 80/443 allowed
- encrypted host disk/volume strongly recommended and required by deployment policy for PHI use
- outbound access needed for container pulls and automatic public TLS certificate issuance, unless an internal TLS design is substituted

## Initial deployment

1. Copy `.env.pilot.example` to `.env.pilot`.
2. Replace every `CHANGE_ME` value with high-entropy secrets.
3. Set `MEDINOTE_DOMAIN` to the real hostname.
4. Set `MEDINOTE_CORS_ORIGINS` to the exact HTTPS origin.
5. Protect `.env.pilot` with filesystem permissions (`chmod 600 .env.pilot`).
6. Run:

   `./deploy/scripts/deploy.sh`

7. Verify:

   `./deploy/scripts/status.sh`

8. Test externally:

   `https://<domain>/api/v1/health`
   `https://<domain>/api/v1/ready`

9. Open the web application and use First-time Pilot Setup exactly once to create the initial administrator.
10. Administrator creates clinician accounts from the organization account workflow/API.

## Pilot administrator procedure
- Bootstrap is permitted only while zero users exist.
- Create the first administrator with a unique institutional email and strong password.
- Create named clinician accounts; do not share credentials.
- Assign the least-privileged role needed.
- Attending/administrator roles can finalize documents; other role permissions remain server-enforced.
- Review the organization audit log routinely.

## Physician onboarding
Each physician should receive:
- unique account
- role assignment
- approved pilot workflow
- statement that MediNote drafts/audits and the physician remains responsible for clinical decisions and final documentation
- instruction not to bypass unresolved safety flags by altering structured truth incorrectly
- escalation contact for software or security concerns

Recommended onboarding exercise:
1. Sign in.
2. Create a synthetic encounter.
3. Import a synthetic chart.
4. Analyze and review Patient Overview.
5. Generate one Progress Note.
6. Edit/approve sections.
7. Run Safety Review.
8. Finalize and copy final text.
9. Sign out.

## Secrets policy
Do not commit `.env.pilot` to source control.
Do not place secrets in Dockerfiles, frontend JavaScript, logs, screenshots, documentation, or support tickets.
Rotate database and backup credentials after suspected exposure.
For a hospital-controlled production environment, move secrets to the organization's approved secrets manager rather than long-lived `.env` files.

## TLS
The included Caddy configuration automatically obtains/renews public TLS certificates when DNS and network access permit.
For an internal hospital domain or private PKI, replace the automatic public TLS configuration with the organization's certificate/ingress standard.
Do not operate a PHI pilot over plain HTTP.

## Security headers
The reverse proxy supplies:
- HSTS
- X-Content-Type-Options
- X-Frame-Options DENY
- no-referrer policy
- restricted browser permissions
- server-header suppression

## Logging policy
Allowed operational logs:
- timestamp
- HTTP method/path template when feasible
- status code
- latency
- service/instance identifiers
- non-PHI error codes

Do not intentionally log:
- chart text
- note bodies
- patient name
- MRN
- DOB
- medication narrative
- Authorization headers or session tokens
- passwords/secrets

Application audit events use IDs and controlled metadata and should remain separate from generic reverse-proxy logs.

## Persistence and encryption
PostgreSQL persists in a Docker volume. The deployment host/volume must use organization-approved encryption at rest for any PHI use.
The application does not claim to provide transparent filesystem/disk encryption itself.

Backups generated by `backup.sh` are additionally encrypted using AES-256-CBC with PBKDF2-derived key material and a deployment-specific passphrase. Store backup passphrases separately from backup files.

## Backup
Run:

`./deploy/scripts/backup.sh`

The script:
- creates a logical `pg_dump`
- compresses it
- encrypts it
- removes plaintext temporary backup data
- applies configured local retention

For a real pilot, schedule backups with the organization's scheduler and copy encrypted backups to approved protected off-host storage.

## Restore / disaster recovery
A restore is a destructive/high-impact operational event and should be performed by an authorized administrator during a defined maintenance period.

1. Stop clinician use of the service.
2. Confirm the correct backup and passphrase.
3. Take a fresh backup if the current database is still available.
4. Restore into a clean/non-production validation database first whenever feasible.
5. Run:

   `./deploy/scripts/restore.sh deploy/backups/<file>.sql.gz.enc`

6. Restart/check services.
7. Verify `/health`, `/ready`, login, encounter access, and one synthetic workflow.
8. Document the recovery event.

Define organization-specific RPO/RTO before the pilot. The included scripts do not by themselves establish an SLA.

## Health checks
- `/api/v1/health` - process/liveness signal
- `/api/v1/ready` - application can reach/query the database

Docker also checks PostgreSQL and API health before dependent services start.

## PHI-safe operational boundaries
Before real PHI is entered, complete institutional review of:
- hosting environment and network segmentation
- encryption at rest/in transit
- identity/MFA/SSO expectations
- vendor/model data processing and BAAs where applicable
- backup destination and retention
- audit retention
- incident response
- vulnerability management
- endpoint/workstation controls
- data retention/deletion
- legal/regulatory classification

## Incident response minimum
For suspected unauthorized access or PHI exposure:
1. preserve relevant audit/security logs
2. revoke affected sessions/accounts
3. isolate affected service if needed
4. rotate exposed credentials/secrets
5. notify the organization's security/privacy incident process
6. document timeline and affected records based on verified evidence
7. do not delete logs/evidence as an informal remediation step

## Pilot go-live checklist
- [ ] `.env.pilot` contains no placeholders
- [ ] server disk/volume encryption confirmed
- [ ] TLS verified in browser
- [ ] database/API not directly internet-exposed
- [ ] test bypass authentication is false
- [ ] API docs disabled unless explicitly required
- [ ] named clinician accounts created
- [ ] backup generated and restore procedure rehearsed on non-production data
- [ ] health/readiness monitoring configured
- [ ] security/privacy/compliance review completed
- [ ] model/vendor PHI handling approved
- [ ] pilot dataset/use protocol approved
- [ ] physician onboarding completed
- [ ] escalation and incident contacts documented
- [ ] validation build/version frozen for pilot

## Known limitations
This package does not yet implement:
- production MFA challenge flow
- enterprise SAML/OIDC/SSO
- secrets-manager integration
- centralized SIEM integration
- automated vulnerability/patch management
- Kubernetes/managed orchestration
- formal key-management-system backed application encryption
- production EHR integration

These are planned enterprise-hardening items and should be addressed according to the pilot organization's risk assessment.
