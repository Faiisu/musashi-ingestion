"""Service entry point."""

import os
from pathlib import Path

from musashi_ingestion.api.server import serve
from musashi_ingestion.config.store import ConfigStore
from musashi_ingestion.pipeline.spool import Spool
from musashi_ingestion.runtime.supervisor import Supervisor


def main():
    username = os.environ.get("OPERATOR_USERNAME", "admin")
    password = os.environ.get("OPERATOR_PASSWORD", "00000000")
    if not username or not password:
        raise SystemExit("OPERATOR_USERNAME and OPERATOR_PASSWORD must be nonempty")
    data_dir = Path(os.environ.get("MUSASHI_DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    config = ConfigStore(data_dir / "config.json")
    spool = Spool(data_dir / "spool.sqlite3")
    supervisor = Supervisor(config, spool)
    bind = os.environ.get("MUSASHI_BIND", "127.0.0.1")
    port = int(os.environ.get("MUSASHI_PORT", "8080"))
    allowed_origins = tuple(origin.strip() for origin in os.environ.get("MUSASHI_ALLOWED_ORIGINS", "").split(",") if origin.strip())
    try:
        serve(bind, port, username, password, config, spool, supervisor,
              os.environ.get("MUSASHI_PUBLIC_ORIGIN") or None, allowed_origins)
    finally:
        spool.close()


if __name__ == "__main__":
    main()
