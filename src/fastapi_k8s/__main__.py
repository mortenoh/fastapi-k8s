"""Allow running with `python -m fastapi_k8s`."""

import uvicorn

from fastapi_k8s.main import app

uvicorn.run(app, host="0.0.0.0", port=8000)
