from typing import Any

import httpx

from app.config import Settings


class Rest:
    """
    Thin PostgREST and Storage client. With a user's access token, row-level
    security applies exactly as it does in the browser; with the service role
    key it bypasses RLS, so callers must filter by the verified user id.
    """

    def __init__(self, settings: Settings, apikey: str, bearer: str, http: httpx.Client | None = None):
        self._http = http or httpx.Client(timeout=30)
        self._base = settings.supabase_url.rstrip("/")
        self._headers = {"apikey": apikey, "Authorization": f"Bearer {bearer}"}

    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        res = self._http.get(f"{self._base}/rest/v1/{table}", params=params, headers=self._headers)
        check(res)
        return res.json()

    def insert(
        self, table: str, rows: list[dict[str, Any]] | dict[str, Any], on_conflict: str | None = None, select: str | None = None
    ) -> list[dict[str, Any]]:
        prefer = ["return=representation"]
        params = {"select": select} if select else {}
        if on_conflict:
            prefer.append("resolution=merge-duplicates")
            params["on_conflict"] = on_conflict
        res = self._http.post(
            f"{self._base}/rest/v1/{table}",
            params=params,
            json=rows,
            headers={**self._headers, "Prefer": ",".join(prefer)},
        )
        check(res)
        return res.json()

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        res = self._http.patch(
            f"{self._base}/rest/v1/{table}",
            params=filters,
            json=patch,
            headers={**self._headers, "Prefer": "return=representation"},
        )
        check(res)
        return res.json()

    def delete(self, table: str, filters: dict[str, str]) -> None:
        res = self._http.delete(f"{self._base}/rest/v1/{table}", params=filters, headers=self._headers)
        check(res)

    def download(self, bucket: str, path: str) -> bytes:
        res = self._http.get(f"{self._base}/storage/v1/object/{bucket}/{path}", headers=self._headers)
        check(res)
        return res.content

    def list_users(self, per_page: int = 1000) -> list[dict[str, Any]]:
        """Every Supabase Auth user; needs the service role key."""
        users: list[dict[str, Any]] = []
        page = 1
        while True:
            res = self._http.get(
                f"{self._base}/auth/v1/admin/users", params={"page": page, "per_page": per_page}, headers=self._headers
            )
            check(res)
            batch = res.json()["users"]
            users += batch
            if len(batch) < per_page:
                return users
            page += 1

    def rpc(self, function: str, args: dict[str, Any]) -> Any:
        res = self._http.post(f"{self._base}/rest/v1/rpc/{function}", json=args, headers=self._headers)
        check(res)
        return res.json() if res.content else None

    def delete_folder(self, bucket: str, folder: str, page: int = 1000) -> None:
        """Deletes every file in `folder` of a Storage bucket, a page at a time."""
        while True:
            res = self._http.post(
                f"{self._base}/storage/v1/object/list/{bucket}",
                json={"prefix": folder, "limit": page},
                headers=self._headers,
            )
            check(res)
            paths = [f"{folder}/{item['name']}" for item in res.json() if item.get("id")]
            if not paths:
                return
            res = self._http.request(
                "DELETE", f"{self._base}/storage/v1/object/{bucket}", json={"prefixes": paths}, headers=self._headers
            )
            check(res)


def user_db(settings: Settings, access_token: str) -> Rest:
    return Rest(settings, settings.supabase_anon_key, access_token)


def service_db(settings: Settings) -> Rest:
    return Rest(settings, settings.supabase_service_role_key, settings.supabase_service_role_key)


def check(res: httpx.Response) -> None:
    """Raises on an error status, with the start of the response body in the message."""
    try:
        res.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise httpx.HTTPStatusError(f"{error}\nResponse body: {res.text[:500]}", request=error.request, response=res) from None
