# User assistant configuration overrides

Add one or more `.yaml` or `.yml` files in this directory. They load after
built-in modules and the optional legacy `../assistant.yaml` file. Files load
alphabetically; use prefixes such as `10-` and `20-` when override order
matters. Nested mappings merge recursively, so only changed keys need to be
included.

Examples:

```yaml
web:
  sites:
    my docs: https://docs.python.org/

shell:
  apps:
    my editor: "app:My Editor"
```

Applications must be explicitly allowlisted. Safe commands remain subject to
the exact-command allowlist and shell safety checks; do not add commands you do
not trust.
