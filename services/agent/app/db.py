import re
from typing import Any

import httpx

from app.config import Settings
from app.constants import HTTP_TIMEOUT

# One connection pool shared by every Rest client and auth check, safe across threads.
HTTP = httpx.Client(timeout=HTTP_TIMEOUT)
# Rows or files read per request when going through all of them.
PAGE_SIZE = 1000
# Characters of an error response body kept in the raised error.
MAX_ERROR_BODY = 500
# The index allowing one queued or running run per user.
ACTIVE_RUN_CONSTRAINT = "agent_runs_one_active_per_user"
CONSTRAINT = re.compile(r'unique constraint \\?"(\w+)')


class Rest:
    """
    Thin PostgREST and Storage client. With a user's access token, row-level
    security applies exactly as it does in the browser; with the service role
    key it bypasses RLS, so callers must filter by the verified user id.
    insert and update return the written rows only when given a select.
    """

    def __init__(self, settings: Settings, apikey: str, bearer: str, http: httpx.Client | None = None):
        self._http = http or HTTP
        self._base = settings.supabase_url.rstrip("/")
        self._headers = {"apikey": apikey, "Authorization": f"Bearer {bearer}"}

    def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        res = self._http.get(f"{self._base}/rest/v1/{table}", params=params, headers=self._headers)
        check(res)
        return res.json()

    def insert(
        self, table: str, rows: list[dict[str, Any]] | dict[str, Any], on_conflict: str | None = None, select: str | None = None
    ) -> list[dict[str, Any]]:
        prefer = ["return=representation" if select else "return=minimal"]
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
        return res.json() if select else []

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> list[dict[str, Any]]:
        res = self._http.patch(
            f"{self._base}/rest/v1/{table}",
            params=filters,
            json=patch,
            headers={**self._headers, "Prefer": "return=representation" if "select" in filters else "return=minimal"},
        )
        check(res)
        return res.json() if "select" in filters else []

    def delete(self, table: str, filters: dict[str, str]) -> None:
        res = self._http.delete(f"{self._base}/rest/v1/{table}", params=filters, headers=self._headers)
        check(res)

    def download(self, bucket: str, path: str) -> bytes:
        res = self._http.get(f"{self._base}/storage/v1/object/{bucket}/{path}", headers=self._headers)
        check(res)
        return res.content

    def rpc(self, function: str, args: dict[str, Any]) -> Any:
        res = self._http.post(f"{self._base}/rest/v1/rpc/{function}", json=args, headers=self._headers)
        check(res)
        return res.json() if res.content else None

    def delete_folder(self, bucket: str, folder: str, page: int = PAGE_SIZE) -> None:
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

    def select_all(self, table: str, params: dict[str, str], page: int = PAGE_SIZE) -> list[dict[str, Any]]:
        """Every matching row in id order, a page at a time past the API's row limit; the select must include id."""
        params = {**params, "order": "id", "limit": str(page)}
        rows: list[dict[str, Any]] = []
        while True:
            batch = self.select(table, params)
            rows += batch
            if len(batch) < page:
                return rows
            params = {**params, "id": f"gt.{batch[-1]['id']}"}


def user_db(settings: Settings, access_token: str) -> Rest:
    return Rest(settings, settings.supabase_anon_key, access_token)


def service_db(settings: Settings) -> Rest:
    return Rest(settings, settings.supabase_service_role_key, settings.supabase_service_role_key)


def check(res: httpx.Response) -> None:
    """Raises on an error status, with the start of the response body in the message."""
    try:
        res.raise_for_status()
    except httpx.HTTPStatusError as error:
        message = f"{error}\nResponse body: {res.text[:MAX_ERROR_BODY]}"
        if res.status_code == 409:
            found = CONSTRAINT.search(res.text)
            raise Conflict(message, request=error.request, response=res, constraint=found[1] if found else None) from None
        raise httpx.HTTPStatusError(message, request=error.request, response=res) from None


class Conflict(httpx.HTTPStatusError):
    """A 409: a row broke a unique constraint, named in `constraint` when the response says which."""

    def __init__(self, message: str, *, request: httpx.Request, response: httpx.Response, constraint: str | None):
        super().__init__(message, request=request, response=response)
        self.constraint = constraint

    @property
    def run_already_going(self) -> bool:
        """Whether the user already has a queued or running run; an unnamed constraint on agent_runs counts too."""
        return self.constraint in (None, ACTIVE_RUN_CONSTRAINT)
