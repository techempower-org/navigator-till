"""Every test run gets its own throwaway session database (set before navigator_till.app is imported)."""
import os
import tempfile

os.environ.setdefault("NT_DB", os.path.join(tempfile.mkdtemp(prefix="navigator-till-test-"), "sessions.db"))
