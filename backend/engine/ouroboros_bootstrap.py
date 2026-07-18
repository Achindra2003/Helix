"""Loader for the vendored Ouroboros engine.

The deep-reasoning engine lives at `backend/engine/ouroboros/` (vendored, so the
backend is self-contained). Its modules use absolute imports (`from ouroboros.x
import ...`), so this puts `backend/engine/` on `sys.path` and imports the
submodules the factory needs, returning the package with them attached.

It deliberately imports only `models`, `presets`, `graph`, and `usage` — never
`server` or `cli` (which call `load_dotenv()` and would walk up to Helix's root
`.env`, the `LLM_PROVIDER=stub` crash from integration gotcha a). The LLM is built
explicitly by the caller, so `providers.get_llm` / `config.get_settings` are never
reached either.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_ouroboros():
    engine_dir = Path(__file__).resolve().parent  # backend/engine
    if str(engine_dir) not in sys.path:
        sys.path.insert(0, str(engine_dir))

    import ouroboros
    import ouroboros.graph  # noqa: F401  (exposes create_ouroboros_graph)
    import ouroboros.memory  # noqa: F401  (exposes get_embedder, for threshold calibration)
    import ouroboros.models  # noqa: F401
    import ouroboros.presets  # noqa: F401
    import ouroboros.usage  # noqa: F401

    return ouroboros
