# engine_components/fail_loud.py -- used by Engine_1.py and patch_engine.py
import logging
import traceback
from pathlib import Path

log = logging.getLogger("engine.critical")
HALT_FLAG = Path(__file__).resolve().parent.parent / "HALT_FLAG"

def fail_loud(context: str, exc: Exception, halt: bool = True) -> None:
    """Capital paths must NEVER swallow. Log, persist halt, re-raise."""
    log.critical("FATAL [%s] %r\n%s", context, exc, traceback.format_exc())
    if halt:
        HALT_FLAG.write_text(f"{context}: {exc}")
        raise exc
