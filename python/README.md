# testisolation (Python)

Uncompromising test isolation: your tests structurally cannot touch your real files, secrets, or git identity -- First-class support for Go, Python with pytest, and TypeScript with Node

This is the pytest plugin.

```bash
pip install testisolation
```

Installing it is adoption: the plugin loads through its `pytest11` entry point
and refuses to run a suite that has not declared its safety stance.

```toml
[tool.pytest.ini_options]
testisolation_sockets = "deny"
testisolation_socket_allowlist = []
testisolation_unix_socket_allowlist = []
testisolation_loopback = "deny"
testisolation_sandbox_required = "false"
```

See the [repository README](https://github.com/stricttools/testisolation) for the full
key reference and what each guard does.

## License

MIT
