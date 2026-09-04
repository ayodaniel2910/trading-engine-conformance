"""The hand-calculated, pure-Python Decimal golden oracle.

Not a production simulator: a small set of unambiguous, hand-calculable
causal execution rules that any conforming engine adapter must also
satisfy. See ``oracle.py`` for the reference ledger and ``cases.py`` for
the JSON golden-case runner.
"""

from __future__ import annotations
