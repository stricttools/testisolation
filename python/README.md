# stricttest (Python)

Uncompromising test isolation: your tests structurally cannot touch your real files, secrets, or git identity -- First-class support for Go, Python with pytest, and TypeScript with Node

This is the pytest plugin.

```bash
pip install stricttest
```

Installing it is adoption: the plugin loads through its `pytest11` entry point
and refuses to run a suite that has not declared its safety stance.

```toml
[tool.pytest.ini_options]
stricttest_sockets = "deny"
stricttest_socket_allowlist = []
stricttest_unix_socket_allowlist = []
stricttest_loopback = "deny"
stricttest_sandbox_required = "false"
```

See the [repository README](https://github.com/smm-h/stricttest) for the full
key reference and what each guard does.

## License

MIT
