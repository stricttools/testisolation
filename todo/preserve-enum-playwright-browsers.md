# `testisolation_preserve` has no entry for the Playwright browser cache

Filed while adopting the pytest plugin in a consumer repo whose suite drives a
headless Chromium through `playwright`.

## Problem

The env floor repoints `HOME` and the XDG set to a throwaway directory, which
is exactly right. Playwright resolves its downloaded browser binaries from
`$XDG_CACHE_HOME/ms-playwright` (falling back to `~/.cache/ms-playwright`), so
after the repoint the browsers are simply gone and every browser-driving test
fails with:

```
BrowserType.launch: Executable doesn't exist at
/tmp/testisolation-env-XXXXXXXX/xdg-cache/ms-playwright/chromium_headless_shell-.../chrome-headless-shell
```

This also bites CI, where the usual `playwright install chromium` step runs
before pytest and therefore installs into the pre-floor cache location.

`testisolation_preserve` exists for exactly this class of problem: read-only
toolchain caches that live under the real home and are not credentials. Its
closed enum currently covers Go, Rust, npm, uv, pip, Python user base and
Gradle, but not Playwright.

Because the enum is deliberately closed (arbitrary variable names are rejected
so a credential vector cannot become preservable by typo — which is the right
design), a consumer cannot add it locally. The only workarounds available in a
consumer repo are worse than the guard:

- resolve the invoking user's home out of `/etc/passwd` (`pwd.getpwuid`) and
  set `PLAYWRIGHT_BROWSERS_PATH` from it — an explicit, source-visible escape
  from the floor, but an escape, and one every consumer with browser tests has
  to reinvent;
- run `playwright install` into the throwaway home on every session — a
  multi-hundred-megabyte download per run;
- keep browser tests out of the floor entirely.

## Suggested resolution

Add one entry to `PRESERVE_VARS`:

```python
"playwright_browsers": ("PLAYWRIGHT_BROWSERS_PATH", "{home}/.cache/ms-playwright"),
```

It fits the existing shape exactly: an env var Playwright already honours, with
a real-home default derived the same way the other ten are. The variable holds
a filesystem path to downloaded binaries; it carries no credential.

Worth checking at the same time whether the Node package's equivalent (Node
suites driving Playwright through `node:test`) needs the same name in its
`preserve` option, so the three-way parity test keeps holding.

## Affected files

- `python/src/testisolation/config.py` (`PRESERVE_VARS`)
- the cross-language parity test that pins the preserve enums
- the preserve-key documentation in the READMEs

## Effort

Small — one enum entry plus the parity/doc updates it pulls in.
