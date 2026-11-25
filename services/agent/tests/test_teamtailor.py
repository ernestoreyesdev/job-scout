import httpx
import pytest
import respx

from app.sources.base import BoardNotFound
from app.sources.teamtailor import TeamtailorSource

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations">
  <channel>
    <title>Axmed</title>
    <item>
      <title>Product Manager</title>
      <description>&lt;p&gt;Lead a new product.&lt;/p&gt;</description>
      <pubDate>Thu, 19 Nov 2026 16:16:49 +0000</pubDate>
      <link>https://axmed.teamtailor.com/jobs/8770908-product-manager</link>
      <remoteStatus>fully</remoteStatus>
      <guid>fad321de</guid>
      <tt:locations>
        <tt:location><tt:name>Spain, Remote</tt:name></tt:location>
        <tt:location><tt:name>Kenya, Remote</tt:name></tt:location>
      </tt:locations>
    </item>
  </channel>
</rss>"""


@respx.mock
def test_fetch_reads_the_rss_feed():
    respx.get("https://axmed.teamtailor.com/jobs.rss").mock(return_value=httpx.Response(200, text=FEED))

    [posting] = TeamtailorSource().fetch("axmed", "axmed")

    assert (posting.source, posting.board, posting.external_id) == ("teamtailor", "axmed", "fad321de")
    assert posting.title == "Product Manager" and posting.company == "Axmed"
    assert posting.url == "https://axmed.teamtailor.com/jobs/8770908-product-manager"
    assert posting.location == "Spain, Remote; Kenya, Remote" and posting.workplace_type == "remote"
    assert posting.description == "Lead a new product."
    assert posting.posted_at and posting.posted_at.isoformat() == "2026-11-19T16:16:49+00:00"


@respx.mock
def test_unknown_board_raises():
    respx.get("https://nope.teamtailor.com/jobs.rss").mock(return_value=httpx.Response(404))

    with pytest.raises(BoardNotFound):
        TeamtailorSource().fetch("nope", "Nope")
