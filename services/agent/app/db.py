from typing import Any

import httpx

from app.config import Settings


class Rest:
    """
    Thin PostgREST and Storage client. With a user's access token, row-level
    security applies exactly as it does in the browser; with the service role
    key it bypasses RLS, so callers must filter by the verified user id.
    """

    def __init__(self, settings: Settings, bearer: str, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=30)
        self._base = settings.supabase_url.rstrip("/")
        self._headers = {"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {bearer}"}

    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        res = self._http.get(f"{self._base}/rest/v1/{table}", params=params, headers=self._headers)
        res.raise_for_status()
        return res.json()

    def insert(self, table: str, rows: list[dict[str, Any]] | dict[str, Any], on_conflict: str | None = None) -> list[dict[str, Any]]:
        prefer = ["return=representation"]
        params = {}
        if on_conflict:
            prefer.append("resolution=merge-duplicates")
            params["on_conflict"] = on_conflict
        res = self._http.post(
            f"{self._base}/rest/v1/{table}",
            params=params,
            json=rows,
            headers={**self._headers, "Prefer": ",".join(prefer)},
        )
        res.raise_for_status()
        return res.json()

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        res = self._http.patch(
            f"{self._base}/rest/v1/{table}",
            params=filters,
            json=patch,
            headers={**self._headers, "Prefer": "return=representation"},
        )
        res.raise_for_status()
        return res.json()

    def delete(self, table: str, filters: dict[str, str]) -> None:
        res = self._http.delete(f"{self._base}/rest/v1/{table}", params=filters, headers=self._headers)
        res.raise_for_status()

    def download(self, bucket: str, path: str) -> bytes:
        res = self._http.get(f"{self._base}/storage/v1/object/{bucket}/{path}", headers=self._headers)
        res.raise_for_status()
        return res.content


def user_db(settings: Settings, access_token: str) -> Rest:
    return Rest(settings, access_token)


def service_db(settings: Settings) -> Rest:
    return Rest(settings, settings.supabase_service_role_key)
