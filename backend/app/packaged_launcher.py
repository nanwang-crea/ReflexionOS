import os

import uvicorn

from app.main import app


def main() -> None:
    host = os.environ.get("REFLEXION_BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("REFLEXION_BACKEND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
