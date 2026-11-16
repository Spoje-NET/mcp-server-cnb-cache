---
name: mcp-server-cnb-cache
description: Look up and convert Czech National Bank (CNB) daily exchange rates via a cnb-cache instance. Use for CZK conversions and historical rates.
---

Use `get_rate` for one day's rate, `get_rate_history` for a range (max 31 days),
`convert_amount` to convert between CZK/foreign currencies and `list_currencies`
to see what is cached. Weekends/holidays have no rate.
