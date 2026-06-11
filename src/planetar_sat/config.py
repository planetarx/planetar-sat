from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CACHE_DIR = Path(os.environ.get("PLANETAR_SAT_CACHE", "data/scenes")).resolve()
DEFAULT_BROKER = os.environ.get("PLANETAR_BROKER", "127.0.0.1:12001")


@dataclass(frozen=True)
class CDSECredentials:
    username: str
    password: str

    @classmethod
    def from_env(cls) -> "CDSECredentials":
        u = os.environ.get("CDSE_USERNAME")
        p = os.environ.get("CDSE_PASSWORD")
        if not u or not p:
            raise RuntimeError(
                "CDSE_USERNAME / CDSE_PASSWORD not set. "
                "Register at https://dataspace.copernicus.eu/ and export both."
            )
        return cls(username=u, password=p)
