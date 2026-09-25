"""testisolation -- always-on test isolation for pytest suites.

The package ships a ``pytest11`` plugin. Installing it is adoption: the plugin
loads automatically and refuses to run a suite that has not declared its safety
stance. See :mod:`testisolation.config` for the ini keys.
"""

from .config import PRESERVE_VARS, REQUIRED_KEYS, Settings
from .socketguard import NetworkBlocked, Policy

__version__ = "0.4.0"

# No ``__all__`` here on purpose. Every name above is defined -- and documented
# -- on its own module's API-reference page; re-listing them here would make the
# package root claim them a second time, double-counting them in documentation
# coverage. The re-exports themselves are the public import path
# (``from testisolation import NetworkBlocked``) and are covered by the suite.
_REEXPORTS = (PRESERVE_VARS, REQUIRED_KEYS, Settings, NetworkBlocked, Policy)
