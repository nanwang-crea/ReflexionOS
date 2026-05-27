import os
import sys

import uvicorn

from app.main import app


def _setup_tiktoken_cache() -> None:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        cache_dir = os.path.join(base, "tiktoken-cache")
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["TIKTOKEN_CACHE_DIR"] = cache_dir


def main() -> None:
    _setup_tiktoken_cache()
    host = os.environ.get("REFLEXION_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("REFLEXION_BACKEND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
