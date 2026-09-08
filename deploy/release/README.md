# Clinistry website release preparation

The workflow builds a website walkthrough ZIP on pull requests, changes to main, or manual runs. It has no AWS permissions and makes no production changes. It must be committed and pushed with its referenced Clinistry website files and tests before GitHub can run it; the draft pull request must be reviewed and merged before automatic main-branch release preparation is active.

Run locally:

```
python -m unittest discover -s deploy/release -p 'test_*.py'
node --test clinistry/website/tests/care-access-model.test.mjs
python deploy/release/package_website.py
```

The release uses nine explicit public assets, sets patient access to walkthrough mode, and includes content checksums. No environment files, backend, credentials, or patient records are packaged. Tests check excluded files, disabled live-care catalog, and fail-closed handling of unknown access modes. These checks supplement source review; they do not certify arbitrary future JavaScript as safe.

## AWS activation remaining

1. Reconcile the deployed Lambda package and routes with this repository before choosing a deployment target. The existing backend is Lambda, not a static S3 site. This ZIP is not a replacement Lambda package.
2. Configure one narrowly scoped GitHub OIDC role in account 416338380996. Bind its trust to the verified repository identity and protected deployment environment. Verify the actual OIDC subject format before creating the trust policy.
3. Add a deployment job only after the target and its read-only validation/rollback procedure are verified. Keep identity, session, PHI, clinical-write, billing, and telemedicine activation settings unchanged.
4. Push the reviewed source and workflow to activate release preparation; test a non-production deployment before publishing to the AWS domain.

GitHub OIDC guide: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws

The intended experience is one reviewed release action instead of repeated CloudShell commands. Initial AWS account access is still necessary to establish that connection. No connection or deployment has been performed by this preparation step.
