# stricttest (Python)

This is the pytest plugin: an always-on test-isolation floor that makes a test
suite structurally unable to reach the real HOME, an ambient credential, the
developer's git identity, or a remote git transport.

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
