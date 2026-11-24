"""Import this first in any test that touches the app: isolates all state in a temp dir."""
import os
import tempfile

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cinestats_test_"))
os.environ.setdefault("TMDB_API_KEY", "test-key-not-real")
os.environ["TRUSTED_PROXY_HOPS"] = "0"
