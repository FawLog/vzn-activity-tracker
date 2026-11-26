#!/usr/bin/env python3
"""Run as owner from an explicitly reviewed release; does not install anything."""
import hashlib
import json
from pathlib import Path
import sys
from worker import CONTROL_FILES
root=Path(sys.argv[1]).resolve()
print(json.dumps({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in CONTROL_FILES},indent=2))
