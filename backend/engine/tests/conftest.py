"""Engine tests import the vendored package the same way the API does: by
putting ``backend/engine`` on ``sys.path`` so ``from ouroboros...`` resolves.
No LLM, no network — everything here runs against fakes.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ENGINE_DIR = Path(__file__).resolve().parents[1]  # backend/engine
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))
