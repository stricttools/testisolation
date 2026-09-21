# Sample consumer

A miniature project that adopts stricttest exactly the way a real repo does:
a `pytest.ini` declaring the five safety keys, a small library that touches the
user's home directory / git / the network, and a normal test suite exercising
it.

`tests/test_sample_consumer.py` in the parent suite copies this tree into a
scratch directory and runs it, proving the isolation does not merely block things
but lets an ordinary suite run green underneath it.

It is deliberately NOT collected by the parent suite (see `collect_ignore` in
`tests/conftest.py`): it must run as its own pytest session, with its own
rootdir and its own stance.
