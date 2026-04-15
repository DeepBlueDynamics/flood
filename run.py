"""Local development entry point — loads .env and starts uvicorn."""

import logging
import os

from dotenv import load_dotenv

load_dotenv()


class _SuppressHealthChecks(logging.Filter):
    def filter(self, record):
        return "/health" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(_SuppressHealthChecks())

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("web.app:app", host="0.0.0.0", port=port, reload=True)
