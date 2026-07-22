import unittest
from unittest.mock import patch

import requests

from search_nnyy import NNYYSearcher


class FakeResponse:
    def __init__(
        self,
        text="",
        payload=None,
        url="https://nnyy.in/",
        status_code=200,
        headers=None,
    ):
        self.text = text
        self._payload = payload or {}
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses=()):
        self.headers = {}
        self.proxies = {}
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f"未为请求准备响应: {url}")
        return self.responses.pop(0)


class NNYYSearcherTests(unittest.TestCase):
    SEARCH_HTML = """
        <div class="lists lists-filter">
          <div class="lists-content"><ul><li>
            <a href="/dianshiju/20229841.html" class="thumbnail">
              <img src="/nnimg2/20229841.jpg">
              <div class="note"><span>第36集</span></div>
              <div class="countrie"><span>2022</span><span>大陆</span></div>
            </a>
            <h2><a href="/dianshiju/20229841.html">点燃我，温暖你</a></h2>
            <footer><span class="rate">7.7</span></footer>
          </li><li>
            <h2><a href="https://example.com/redirect.html">外部结果</a></h2>
          </li></ul></div>
        </div>
    """
    DETAIL_HTML = """
        <h1 class="product-title">点燃我，温暖你 <span>(2022)</span></h1>
        <ul id="eps-ul">
          <li ep_slug="ep2"><a>第02集</a></li>
          <li ep_slug="ep1"><a>第01集</a></li>
          <li ep_slug="cai_dan"><a>彩蛋</a></li>
        </ul>
        <script>
          var url = '/_gp/{0}/{1}'.replace('{0}', '20229841').replace('{1}', ep_slug);
        </script>
    """

    def test_search_bootstraps_home_and_normalizes_results(self):
        session = FakeSession([
            FakeResponse(url="https://nnyy.in/"),
            FakeResponse(
                text=self.SEARCH_HTML,
                url="https://nnyy.in/so?q=%E7%82%B9%E7%87%83%E6%88%91",
            ),
        ])
        engine = NNYYSearcher(session=session)

        results = engine.search("点燃我", verbose=False)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "点燃我，温暖你")
        self.assertEqual(results[0]["category"], "电视剧")
        self.assertEqual(results[0]["remarks"], "第36集")
        self.assertEqual(results[0]["cover_url"], "https://nnyy.in/nnimg2/20229841.jpg")
        self.assertEqual(session.calls[0][0], "https://nnyy.in/")
        self.assertEqual(session.calls[1][1]["params"], {"q": "点燃我"})

    def test_detail_parser_builds_naturally_sorted_api_urls(self):
        engine = NNYYSearcher(session=FakeSession())

        detail = engine.parse_detail_episodes(
            self.DETAIL_HTML,
            "https://nnyy.in/dianshiju/20229841.html",
        )

        self.assertEqual(detail["video_id"], "20229841")
        self.assertEqual(detail["title"], "点燃我，温暖你")
        self.assertEqual(
            detail["episodes"],
            [
                ("第01集", "https://nnyy.in/_gp/20229841/ep1"),
                ("第02集", "https://nnyy.in/_gp/20229841/ep2"),
                ("彩蛋", "https://nnyy.in/_gp/20229841/cai_dan"),
            ],
        )

    def test_episode_payload_filters_invalid_and_duplicate_urls(self):
        payload = {
            "video_plays": [
                {"src_site": "hnzy", "play_data": "https://cdn.example/1.m3u8"},
                {"src_site": "hnzy", "play_data": "https://cdn.example/1.m3u8"},
                {"src_site": "hnzy", "play_data": "https://cdn.example/backup.m3u8"},
                {"src_site": "bad", "play_data": "javascript:alert(1)"},
                {"src_site": "mp4", "play_data": "https://cdn.example/1.mp4"},
            ]
        }

        self.assertEqual(
            NNYYSearcher.parse_episode_payload(payload),
            [("hnzy", "https://cdn.example/1.m3u8")],
        )

    def test_routes_are_grouped_by_source_and_mark_partial_routes(self):
        engine = NNYYSearcher(session=FakeSession())
        episodes = [
            ("第01集", "https://nnyy.in/_gp/42/ep1"),
            ("第02集", "https://nnyy.in/_gp/42/ep2"),
            ("彩蛋", "https://nnyy.in/_gp/42/cai_dan"),
        ]

        def sources(api_url, _detail_url):
            if api_url.endswith("ep1"):
                return [
                    ("hnzy", "https://cdn.example/hn-1.m3u8"),
                    ("gszy", "https://cdn.example/gs-1.m3u8"),
                ]
            if api_url.endswith("ep2"):
                return [("hnzy", "https://cdn.example/hn-2.m3u8")]
            return [("gszy", "https://cdn.example/gs-extra.m3u8")]

        with patch.object(engine, "fetch_episode_sources", side_effect=sources):
            routes = engine.build_routes(
                episodes,
                "https://nnyy.in/dianshiju/42.html",
                max_workers=2,
            )

        self.assertEqual(routes["HN · hnzy"]["total"], 3)
        self.assertEqual(len(routes["HN · hnzy"]["episodes"]), 2)
        self.assertEqual(routes["HN · hnzy"]["regular_total"], 2)
        self.assertEqual(routes["HN · hnzy"]["special_total"], 1)
        self.assertEqual(routes["HN · hnzy"]["regular_count"], 2)
        self.assertEqual(routes["HN · hnzy"]["special_count"], 0)
        self.assertEqual(routes["GS · gszy"]["total"], 3)
        self.assertEqual(len(routes["GS · gszy"]["episodes"]), 2)
        self.assertEqual(routes["GS · gszy"]["regular_count"], 1)
        self.assertEqual(routes["GS · gszy"]["special_count"], 1)

    def test_episode_api_retries_after_rate_limit(self):
        payload = {
            "video_plays": [
                {"src_site": "hnzy", "play_data": "https://cdn.example/1.m3u8"}
            ]
        }
        session = FakeSession([
            FakeResponse(status_code=429, headers={"Retry-After": "0"}),
            FakeResponse(payload=payload),
        ])
        engine = NNYYSearcher(session=session)
        engine.API_REQUEST_INTERVAL = 0
        engine.RATE_LIMIT_BASE_WAIT = 0

        sources = engine.fetch_episode_sources(
            "https://nnyy.in/_gp/42/ep1",
            "https://nnyy.in/dianshiju/42.html",
        )

        self.assertEqual(sources, [("hnzy", "https://cdn.example/1.m3u8")])
        self.assertEqual(len(session.calls), 2)

    def test_external_detail_url_is_rejected_without_request(self):
        session = FakeSession()
        engine = NNYYSearcher(session=session)

        self.assertEqual(engine.fetch_detail_page("https://example.com/video.html"), "")
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
