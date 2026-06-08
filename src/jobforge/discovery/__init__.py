"""Job source adapters.

Each adapter is responsible for one external source. The adapter layer is
intentionally narrow: `fetch_jobs()` returns `list[RawJob]` and that's it.
Persistence, dedup, and matching live downstream in the discovery service.

The split between `fetch_jobs()` (network) and `parse(payload)` (pure) lets
tests cover normalization with stored fixtures and no live network.
"""
from __future__ import annotations
