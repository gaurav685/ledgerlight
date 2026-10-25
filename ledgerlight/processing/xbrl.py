"""XBRL parsing: DEFERRED. Not implemented in Phase 1.

Checked, not assumed: `find data/raw -iname "*.xml" -o -iname "*.xbrl"`
against the full 237-document Phase 0/Correction-1 corpus returns zero
results. No real XBRL file exists in the corpus, and `sources.yaml` does
not record a legitimately-obtained XBRL source either (BSE/NSE XBRL
filing endpoints are both BLOCKED — see docs/data/source-inventory.md).

Building a parser now would mean testing it only against invented XBRL
fixtures, which the Phase 1 brief explicitly rules out ("Do not build a
parser tested only on invented data"). Deferred until a real XBRL source
becomes available (most likely: an official BSE/NSE data-licensing
relationship — see docs/data/acquisition-strategy.md decision #2).
"""
