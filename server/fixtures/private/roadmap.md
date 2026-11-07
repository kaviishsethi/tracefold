# Northwind Relay — 2027 platform roadmap (internal)

## Summary

In the first half of 2027 we will retire the Harbor ingestion cluster and move every tenant onto the
Lantern streaming tier, starting with the twelve logistics customers that still depend on nightly batch
exports. Lantern migration windows will be scheduled per tenant so that no customer loses more than
forty minutes of event history during cutover.

## Pricing

The enterprise list price rises to 41,000 dollars per year in March, with grandfathered renewals for
accounts signed before the Harbor deprecation notice.

## Hiring

We plan to open three platform engineering roles focused on stream compaction.
