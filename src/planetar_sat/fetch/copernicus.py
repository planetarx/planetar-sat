"""Copernicus Data Space Ecosystem (CDSE) Sentinel-1 GRD fetcher.

Uses CDSE's OData catalogue (https://catalogue.dataspace.copernicus.eu/odata/v1)
to find Sentinel-1 GRD products intersecting an AOI within a date window, then
downloads the zipped SAFE archive via the OData $value endpoint.

Auth: CDSE uses an OAuth2 password grant against Keycloak.
See https://documentation.dataspace.copernicus.eu/APIs/Token.html
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from planetar_sat.config import CDSECredentials
from planetar_sat.fetch.aoi import AOI

log = logging.getLogger(__name__)

ODATA_BASE = "https://catalogue.dataspace.copernicus.eu/odata/v1"
DOWNLOAD_BASE = "https://download.dataspace.copernicus.eu/odata/v1"
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"


@dataclass
class Product:
    id: str
    name: str
    content_length: int
    sensing_start: datetime
    footprint_wkt: str

    @property
    def scene_id(self) -> str:
        """The .SAFE basename without extension — stable identifier across runs."""
        return self.name.removesuffix(".SAFE")


class CDSEClient:
    def __init__(self, creds: CDSECredentials, http: httpx.Client | None = None):
        self.creds = creds
        self.http = http or httpx.Client(timeout=60.0)
        self._token: str | None = None
        self._token_exp: datetime | None = None

    def _get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and self._token_exp and self._token_exp > now + timedelta(seconds=30):
            return self._token
        r = self.http.post(
            TOKEN_URL,
            data={
                "client_id": "cdse-public",
                "grant_type": "password",
                "username": self.creds.username,
                "password": self.creds.password,
            },
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_exp = now + timedelta(seconds=int(body.get("expires_in", 600)))
        return self._token

    def search_grd(
        self,
        aoi: AOI,
        days: int = 3,
        max_results: int = 20,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Product]:
        """List Sentinel-1 GRD products intersecting AOI.

        If both `start` and `end` are given, that window is used directly —
        useful for historical replay. Otherwise the window is the last
        `days` days.
        """
        if end is None:
            end = datetime.now(timezone.utc)
        if start is None:
            start = end - timedelta(days=days)
        wkt = aoi.to_wkt_polygon()
        filt = (
            "Collection/Name eq 'SENTINEL-1' "
            f"and OData.CSC.Intersects(area=geography'SRID=4326;{wkt}') "
            f"and ContentDate/Start gt {start.strftime('%Y-%m-%dT%H:%M:%S.000Z')} "
            f"and ContentDate/Start lt {end.strftime('%Y-%m-%dT%H:%M:%S.000Z')} "
            "and contains(Name,'GRD')"
        )
        params = {
            "$filter": filt,
            "$orderby": "ContentDate/Start desc",
            "$top": str(max_results),
        }
        r = self.http.get(f"{ODATA_BASE}/Products", params=params)
        r.raise_for_status()
        out: list[Product] = []
        for item in r.json().get("value", []):
            out.append(
                Product(
                    id=item["Id"],
                    name=item["Name"],
                    content_length=int(item.get("ContentLength", 0)),
                    sensing_start=datetime.fromisoformat(
                        item["ContentDate"]["Start"].replace("Z", "+00:00")
                    ),
                    footprint_wkt=item.get("Footprint", ""),
                )
            )
        log.info("CDSE returned %d Sentinel-1 GRD products for AOI %s", len(out), aoi.name)
        return out

    def download(self, product: Product, dest_dir: Path) -> Path:
        """Stream a product's .SAFE.zip to dest_dir/<scene_id>.zip. Returns the path."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_path = dest_dir / f"{product.scene_id}.zip"
        if out_path.exists() and out_path.stat().st_size == product.content_length:
            log.info("cache hit: %s", out_path.name)
            return out_path
        url = f"{DOWNLOAD_BASE}/Products({product.id})/$value"
        token = self._get_token()
        with self.http.stream("GET", url, headers={"Authorization": f"Bearer {token}"}) as r:
            r.raise_for_status()
            tmp = out_path.with_suffix(".zip.part")
            with tmp.open("wb") as fh:
                for chunk in r.iter_bytes(chunk_size=1 << 20):
                    fh.write(chunk)
            tmp.rename(out_path)
        log.info("downloaded %s (%d bytes)", out_path.name, out_path.stat().st_size)
        return out_path
