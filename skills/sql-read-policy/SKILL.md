---
name: sql-read-policy
description: Read-only SQL policy for the stock trading agent. Use when querying market, strategy, trading, or ops tables.
---

# SQL Read Policy

## Allowed

- read-only inspection
- schema description
- targeted aggregates
- narrow date-range lookups
- saved reports

## Not Allowed

- `insert`
- `update`
- `delete`
- `drop`
- `alter`
- `truncate`
- unrestricted full-table scans when a narrower query is possible

## Query Rules

- Filter by symbol, date, strategy, or run id whenever possible.
- Prefer recent windows over whole-history scans.
- State when a result may be partial because of the selected window.

## Safety Rule

If a request mixes analysis with mutation, do the read-only part and refuse the mutation.
