# Test fixtures

Every file here is synthetic and written for Tracefold tests. Company names (Halyard Freight), plans,
identifiers and secret-like values are invented; none are real credentials, people or leaked material.

- `public/` — pages served to the fixture provider as "public sources".
- `private/` — reference inputs: a copied passage, same-topic and unrelated negatives, boilerplate, and
  risky/corrected code for preventive-review and recheck tests, and `aws_config.py` with a made-up AWS
  access key ID for remediation tests.
