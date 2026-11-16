# mcp-server-cnb-cache

MCP server (stdio) giving AI assistants access to Czech National Bank (CNB)
exchange rates through a [cnb-cache](https://github.com/Spoje-NET/CNB-Cache) instance.
Rates are CZK per `amount` units of the foreign currency (JPY is quoted per 100).

## Installation

```shell
sudo apt install mcp-server-cnb-cache            # the server
sudo apt install mcprack-mcp-server-cnb-cache    # registers it in mcprack
```

## Configuration

| Variable | Secret | Default | Meaning |
|---|---|---|---|
| `CNB_CACHE_URL` | no | `http://localhost/cnb-cache/` | Base URL of the cnb-cache web interface |
| `CNB_CACHE_TIMEOUT` | no | `10` | Request timeout in seconds |
| `CNB_CACHE_TRANSPORT` | no | `stdio` | MCP transport |
| `CNB_CACHE_READ_ONLY` | no | `true` | Accepted for uniformity; all tools are read-only |

## Tools

| Tool | Annotation class |
|---|---|
| `get_rate` | READ_ONLY |
| `list_currencies` | READ_ONLY |
| `convert_amount` | READ_ONLY |
| `get_rate_history` | READ_ONLY (max 31 days) |

## Development

```shell
pytest
mcprack server probe mcp-server-cnb-cache
```
