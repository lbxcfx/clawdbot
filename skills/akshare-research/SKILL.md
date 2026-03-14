---
name: akshare-research
description: Research guidance for using AkShare with the stock trading agent. Use when checking ETF market data, validating symbols, or deciding whether to read local storage or re-sync data.
---

# AkShare Research

## Source Priority

Use sources in this order:

1. local database
2. latest sync status
3. targeted AkShare fetch only when sync or gap repair is actually needed

Do not repeatedly fetch online data when the local store already contains the required daily bars.

## Phase-1 Universe

Only work with:

- A-share listed ETFs
- clear industry ETFs
- symbols present in the configured universe table

Reject symbols outside that scope.

## Data Rules

- Daily bars are the source of truth for phase 1.
- Keep naming consistent across symbol, name, sector, and trade date.
- Treat missing bars, duplicate bars, and short history as data-quality issues.

## Research Output

When asked for research, clearly separate:

- data facts from the local store
- fresh sync status
- conclusions drawn from those facts
