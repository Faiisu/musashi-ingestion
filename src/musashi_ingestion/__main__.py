"""Service entry point."""

import os
from pathlib import Path

from musashi_ingestion.api.server import serve
from musashi_ingestion.config.store import ConfigStore
from musashi_ingestion.pipeline.spool import Spool
from musashi_ingestion.runtime.supervisor import Supervisor


def main():
    token = os.environ.get("OPERATOR_TOKEN", "")
    if not token:
        raise SystemExit("OPERATOR_TOKEN must be set")
    data_dir = Path(os.environ.get("MUSASHI_DATA_DIR", "./data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    config = ConfigStore(data_dir / "config.json")
    spool = Spool(data_dir / "spool.sqlite3")
    supervisor = Supervisor(config, spool)
    bind = os.environ.get("MUSASHI_BIND", "127.0.0.1")
    port = int(os.environ.get("MUSASHI_PORT", "8080"))
    try:
        serve(bind, port, token, config, spool, supervisor)
    finally:
        spool.close()


if __name__ == "__main__":
    main()
