import hashlib
import unittest
from unittest.mock import patch

import requests

from search_iyf import IYFSearcher


class FakeResponse:
    def __init__(self, text="", payload=None, status_code=200):
        self.text = text
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")
        return None

    def json(self):
        return self._payload


class FakeCookies(dict):
    def update(self, mapping=(), **kwargs):
        super().update(mapping, **kwargs)


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.proxies = {}
        self.cookies = FakeCookies()
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class IYFSearcherTests(unittest.TestCase):
    HOME_HTML = """
        <script>window.data = {"config":[{"pConfig":{
          "publicKey":"public-value","privateKey":["private-value"]
        }}]};</script>
    """

    PLAY_PAYLOAD = {
        "ret": 200,
        "data": {
            "code": 0,
            "info": [{
                "flvPathList": [
                    {"isHls": False, "result": "https://cdn.example/a.mp4"},
                    {
                        "isHls": True,
                        "result": "https://cdn.example/fallback.m3u8",
                    },
                ],
                "clarity": [
                    {
                        "title": "720",
                        "description": "高清",
                        "isVIP": True,
                        "isEnabled": False,
                        "path": None,
                    },
                    {
                        "title": "576",
                        "description": "标清",
                        "isVIP": False,
                        "isEnabled": True,
                        "path": {
                            "isHls": True,
                            "result": "https://cdn.example/sd.m3u8",
                        },
                    },
                ],
            }],
        },
    }

    def test_parse_home_keys_and_signatures(self):
        public_key, private_key = IYFSearcher.parse_home_keys(self.HOME_HTML)
        self.assertEqual((public_key, private_key), ("public-value", "private-value"))
        expected_search = hashlib.md5(
            b"public-value&cinema=1&cid=0,1&private-value"
        ).hexdigest()
        self.assertEqual(
            IYFSearcher.build_search_signature(public_key, private_key),
            expected_search,
        )
        expected_play = hashlib.md5(
            b"public-value&cinema=1&id=t0uwofspfa9&a=0&lang=none"
            b"&usersign=1&region=jp&device=1&ismastersupport=0&private-value"
        ).hexdigest()
        self.assertEqual(
            IYFSearcher.build_play_signature(public_key, private_key, "T0UWOfSpFa9"),
            expected_play,
        )

    def test_pick_sd_m3u8_prefers_576(self):
        play_info = self.PLAY_PAYLOAD["data"]["info"][0]
        self.assertEqual(
            IYFSearcher.pick_sd_m3u8(play_info),
            "https://cdn.example/sd.m3u8",
        )

    def test_search_refreshes_keys_and_normalizes_results(self):
        payload = {
            "ret": 200,
            "data": {
                "code": 0,
                "info": [{
                    "result": [{
                        "title": "野狗骨头",
                        "atypeName": "电视剧",
                        "postTime": "2026-01-01T00:00:00",
                        "regional": "大陆",
                        "cid": "爱情",
                        "starring": "演员甲,演员乙",
                        "directed": "导演甲",
                        "score": "8.5",
                        "lastName": "21",
                        "contxt": "content-key",
                        "videoClassID": "0,1,4,146",
                        "languagesPlayList": {
                            "playList": [{"id": 1, "key": "episode-key", "name": "01"}]
                        },
                    }]
                }],
            },
        }
        session = FakeSession([
            FakeResponse(text=self.HOME_HTML),
            FakeResponse(payload=payload),
        ])
        engine = IYFSearcher(cookie={"cf_clearance": "value"}, session=session)

        results = engine.search("野狗骨头", verbose=False)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "野狗骨头")
        # 搜索阶段不再同步补全剧集，先用搜索接口里的简要列表快速返回。
        self.assertEqual(results[0]["total"], 1)
        self.assertEqual(results[0]["episodes"][0]["key"], "episode-key")
        self.assertEqual(session.cookies["cf_clearance"], "value")
        home_call, search_call = session.calls
        self.assertEqual(home_call[0], "get")
        self.assertEqual(search_call[0], "post")
        self.assertEqual(search_call[2]["params"]["tags"], "野狗骨头")
        self.assertEqual(search_call[2]["data"]["tags"], "%E9%87%8E%E7%8B%97%E9%AA%A8%E5%A4%B4")
        self.assertEqual(search_call[2]["data"]["pub"], "public-value")
        self.assertEqual(
            search_call[2]["data"]["vv"],
            hashlib.md5(b"public-value&cinema=1&cid=0,1&private-value").hexdigest(),
        )

    def test_extract_item_requests_play_and_stores_sd_m3u8(self):
        session = FakeSession([
            FakeResponse(text=self.HOME_HTML),
            FakeResponse(payload={
                "ret": 200,
                "data": {
                    "code": 0,
                    "info": [{
                        "playList": [{"id": 2, "key": "T0UWOfSpFa9", "name": "02"}]
                    }],
                },
            }),
            FakeResponse(payload=self.PLAY_PAYLOAD),
        ])
        engine = IYFSearcher(session=session)
        item = {
            "title": "野狗骨头",
            "content_key": "2aEAXYC9gdB",
            "video_class_id": "0,1,4,146",
            "episodes": [{"id": 2, "key": "T0UWOfSpFa9", "name": "02"}],
        }

        results = engine.extract_item(item)

        self.assertEqual(results, {"野狗骨头_标清_02": "https://cdn.example/sd.m3u8"})
        self.assertEqual(engine.get_result()["野狗骨头_标清_02"], "https://cdn.example/sd.m3u8")
        home_call, playlist_call, play_call = session.calls
        self.assertEqual(home_call[0], "get")
        self.assertIn("languagesplaylist", playlist_call[1])
        self.assertEqual(play_call[0], "get")
        self.assertTrue(play_call[1].endswith("/v3/video/play") or "/v3/video/play?" in play_call[1])
        self.assertEqual(play_call[2]["params"]["id"], "T0UWOfSpFa9")
        self.assertEqual(play_call[2]["params"]["pub"], "public-value")
        self.assertEqual(
            play_call[2]["params"]["vv"],
            IYFSearcher.build_play_signature("public-value", "private-value", "T0UWOfSpFa9"),
        )

    def test_refresh_keys_falls_back_to_drissionpage_on_403(self):
        session = FakeSession([
            FakeResponse(text="Just a moment...", status_code=403),
        ])
        engine = IYFSearcher(session=session)
        with patch.object(engine, "bypass_cloudflare", return_value=("pub", "priv")) as bypass:
            public_key, private_key = engine.refresh_keys(allow_browser=True)
        self.assertEqual((public_key, private_key), ("pub", "priv"))
        bypass.assert_called_once()

    def test_get_episode_m3u8_retries_on_timeout(self):
        session = FakeSession([
            requests.exceptions.ReadTimeout(
                "HTTPSConnectionPool(host='m10.iyf.tv', port=443): Read timed out."
            ),
            FakeResponse(text=self.HOME_HTML),
            FakeResponse(payload=self.PLAY_PAYLOAD),
        ])
        engine = IYFSearcher(session=session)
        engine.public_key = "public-value"
        engine.private_key = "private-value"
        engine.NETWORK_RETRY_WAIT = 0.01
        engine.PLAY_INTERVAL = 0

        url = engine.get_episode_m3u8("2aEAXYC9gdB", "T0UWOfSpFa9")

        self.assertEqual(url, "https://cdn.example/sd.m3u8")
        self.assertEqual(len(session.calls), 3)
        self.assertTrue(session.calls[0][1].endswith("/v3/video/play"))
        self.assertTrue(session.calls[2][1].endswith("/v3/video/play"))

    def test_get_episode_m3u8_retries_on_rate_limit(self):
        rate_limited = {
            "ret": 200,
            "data": {"code": 1, "msg": "访问过量", "info": []},
        }
        session = FakeSession([
            FakeResponse(payload=rate_limited),
            FakeResponse(text=self.HOME_HTML),
            FakeResponse(payload=self.PLAY_PAYLOAD),
        ])
        engine = IYFSearcher(session=session)
        engine.public_key = "public-value"
        engine.private_key = "private-value"
        engine.RATE_LIMIT_BASE_WAIT = 0.01
        engine.PLAY_INTERVAL = 0
        play_url = "https://www.iyf.tv/play/2aEAXYC9gdB?id=T0UWOfSpFa9"
        challenge_url = IYFSearcher.build_challenge_url("2aEAXYC9gdB", "T0UWOfSpFa9")

        with patch.object(
            engine,
            "bypass_cloudflare",
            return_value=("public-value", "private-value"),
        ) as bypass:
            url = engine.get_episode_m3u8("2aEAXYC9gdB", "T0UWOfSpFa9")

        self.assertEqual(url, "https://cdn.example/sd.m3u8")
        bypass.assert_called()
        self.assertEqual(bypass.call_args.kwargs.get("url"), challenge_url)
        self.assertEqual(bypass.call_args.kwargs.get("require_keys"), False)
        self.assertIn("/challenge?", challenge_url)
        self.assertEqual(len(session.calls), 3)
        self.assertEqual(session.calls[0][0], "get")
        self.assertTrue(session.calls[0][1].endswith("/v3/video/play"))
        self.assertEqual(session.calls[1][0], "get")
        self.assertEqual(session.calls[2][0], "get")
        self.assertTrue(session.calls[2][1].endswith("/v3/video/play"))

    def test_build_play_page_url(self):
        self.assertEqual(
            IYFSearcher.build_play_page_url("8G3krGD2FL5", "g7lTuzcBvGC"),
            "https://www.iyf.tv/play/8G3krGD2FL5?id=g7lTuzcBvGC",
        )
        self.assertEqual(
            IYFSearcher.build_play_page_url("8G3krGD2FL5"),
            "https://www.iyf.tv/play/8G3krGD2FL5",
        )

    def test_build_challenge_url(self):
        url = IYFSearcher.build_challenge_url("8G3krGD2FL5", "g7lTuzcBvGC")
        self.assertIn("https://www.iyf.tv/challenge?", url)
        self.assertIn("return=", url)
        self.assertIn("8G3krGD2FL5", url)
        self.assertIn("g7lTuzcBvGC", url)
        self.assertIn("triggerindex=", url)
        self.assertTrue(IYFSearcher._is_challenge_url(url))
        self.assertFalse(IYFSearcher._is_challenge_url("https://www.iyf.tv/play/x"))

    def test_challenge_bypass_success_requires_leaving_challenge_url(self):
        class FakePage:
            def __init__(self, url):
                self.url = url

        engine = IYFSearcher()
        challenge = (
            "https://www.iyf.tv/challenge?return=%2Fplay%2F8G3krGD2FL5"
            "%3Fid%3Dg7lTuzcBvGC&triggerindex=%E8%AE%BF%E9%97%AE%E8%BF%87%E9%87%8F"
        )
        play = "https://www.iyf.tv/play/8G3krGD2FL5?id=g7lTuzcBvGC"
        self.assertFalse(engine._challenge_bypass_success(FakePage(challenge), True))
        self.assertTrue(engine._challenge_bypass_success(FakePage(play), True))
        self.assertTrue(
            IYFSearcher._turnstile_checkbox_ready_from_html("请点击下方按钮确保您不是机器人")
        )
        self.assertTrue(
            IYFSearcher._turnstile_checkbox_ready_from_html("检测到您的流量异常")
        )
        # shadow 内文案不可作为唯一条件，但出现也应判定就绪
        self.assertTrue(IYFSearcher._turnstile_checkbox_ready_from_html("请验证您是真人"))

    def test_fetch_play_info_opens_play_page_on_cf(self):
        cf_html = "<html>Just a moment... challenge-platform</html>"
        session = FakeSession([
            FakeResponse(text=cf_html, status_code=403),
            FakeResponse(payload=self.PLAY_PAYLOAD),
        ])
        engine = IYFSearcher(session=session)
        engine.public_key = "public-value"
        engine.private_key = "private-value"
        play_url = "https://www.iyf.tv/play/8G3krGD2FL5?id=g7lTuzcBvGC"

        with patch.object(engine, "bypass_cloudflare", return_value=("public-value", "private-value")) as bypass:
            with patch.object(
                engine,
                "refresh_keys",
                return_value=("public-value", "private-value"),
            ):
                play_info = engine.fetch_play_info("8G3krGD2FL5", "g7lTuzcBvGC")

        self.assertEqual(IYFSearcher.pick_sd_m3u8(play_info), "https://cdn.example/sd.m3u8")
        bypass.assert_called_once()
        self.assertEqual(bypass.call_args.kwargs.get("url"), play_url)
        self.assertEqual(bypass.call_args.kwargs.get("require_keys"), False)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(session.calls[0][2]["headers"]["referer"], play_url)

    def test_response_is_cf_challenge(self):
        self.assertTrue(
            IYFSearcher._response_is_cf_challenge(
                FakeResponse(text="Just a moment...", status_code=403)
            )
        )
        self.assertFalse(
            IYFSearcher._response_is_cf_challenge(
                FakeResponse(payload={"ok": True}, status_code=200)
            )
        )

    def test_enrich_episodes_uses_languagesplaylist(self):
        playlist_payload = {
            "ret": 200,
            "data": {
                "code": 0,
                "info": [{
                    "playList": [
                        {"id": 1, "key": "k01", "name": "01"},
                        {"id": 2, "key": "k12", "name": "12"},
                        {"id": 3, "key": "k27", "name": "27"},
                    ]
                }],
            },
        }
        session = FakeSession([FakeResponse(payload=playlist_payload)])
        engine = IYFSearcher(session=session)
        engine.public_key = "public-value"
        engine.private_key = "private-value"
        item = {
            "title": "点燃我温暖你",
            "content_key": "8G3krGD2FL5",
            "video_class_id": "0,1,4,146",
            "episodes": [{"id": 1, "key": "k01", "name": "01"}],
            "total": 1,
        }

        engine.enrich_episodes(item)

        self.assertEqual(item["total"], 3)
        self.assertEqual([ep["name"] for ep in item["episodes"]], ["01", "12", "27"])
        self.assertIn("languagesplaylist", session.calls[0][1])
        self.assertIn("cid=0,1,4,146", session.calls[0][1])


if __name__ == "__main__":
    unittest.main()
