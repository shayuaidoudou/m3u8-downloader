import unittest
from unittest.mock import Mock, patch

from search import (
    AIGUA_CHANNEL,
    CHANNEL_INPUT_COOKIE,
    CHANNEL_INPUT_NONE,
    CHANNEL_INPUT_TYPE,
    IYF_CHANNEL,
    MOFA_CHANNEL,
    NCAT_CHANNEL,
    SEARCH_CHANNELS,
    AiGuaEngine,
    channel_requires_refresh,
    create_search_engine,
    get_channel_input_mode,
    search_with_engine,
)


class FakeResponse:
    def __init__(self, text='', payload=None):
        self.text = text
        self.encoding = None
        self._payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses=None):
        self.headers = {}
        self.proxies = {}
        self.responses = list(responses or [])
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError(f'未为请求准备响应: {url}')
        return self.responses.pop(0)


class SearchChannelTests(unittest.TestCase):
    def test_channel_metadata(self):
        self.assertEqual(SEARCH_CHANNELS, (AIGUA_CHANNEL, NCAT_CHANNEL, MOFA_CHANNEL, IYF_CHANNEL))
        self.assertEqual(get_channel_input_mode(AIGUA_CHANNEL), CHANNEL_INPUT_TYPE)
        self.assertEqual(get_channel_input_mode(NCAT_CHANNEL), CHANNEL_INPUT_COOKIE)
        self.assertEqual(get_channel_input_mode(MOFA_CHANNEL), CHANNEL_INPUT_NONE)
        self.assertEqual(get_channel_input_mode(IYF_CHANNEL), CHANNEL_INPUT_COOKIE)
        self.assertFalse(channel_requires_refresh(AIGUA_CHANNEL))
        self.assertTrue(channel_requires_refresh(NCAT_CHANNEL))
        self.assertTrue(channel_requires_refresh(IYF_CHANNEL))

    def test_aigua_proxy_is_applied_before_requests(self):
        session = FakeSession()
        AiGuaEngine(
            proxy_config={
                'enabled': True,
                'type': 'HTTP',
                'host': '127.0.0.1',
                'port': 7897,
            },
            session=session,
            bootstrap=False,
        )
        expected = 'http://127.0.0.1:7897'
        self.assertEqual(session.proxies, {'http': expected, 'https': expected})

    def test_aigua_search_parses_movie_and_series_links(self):
        html = """
            <a class="SSjgImg" href="/video/movie?video_id=1"></a>
            <a title="剧集" href="/video/series?video_id=2"></a>
            <a title="无效" href="javascript:void(0)"></a>
        """
        session = FakeSession([FakeResponse(html), FakeResponse(html)])
        engine = AiGuaEngine(session=session, bootstrap=False)

        self.assertEqual(
            engine.search('测试', choice=0),
            ['https://aigua.tv/video/movie?video_id=1'],
        )
        self.assertEqual(
            engine.search('测试', choice=1),
            ['https://aigua.tv/video/series?video_id=2'],
        )

    def test_aigua_m3u8_uses_parsed_video_id_and_collects_results(self):
        detail = "<script>arrIndex['chapterId'] = '12';</script>"
        payload = {'data': {'urlinfo': {'resource_url': 'https://cdn.example/video.m3u8'}}}
        session = FakeSession([FakeResponse(detail), FakeResponse(payload=payload)])
        engine = AiGuaEngine(session=session, bootstrap=False)

        result = engine.get_m3u8('https://aigua.tv/video/detail?video_id=42')

        self.assertEqual(result, 'https://cdn.example/video.m3u8')
        self.assertEqual(session.calls[1][1]['params']['videoId'], '42')
        self.assertEqual(engine.get_result(), {'12': result})

    def test_aigua_rejects_external_detail_urls(self):
        session = FakeSession()
        engine = AiGuaEngine(session=session, bootstrap=False)

        self.assertEqual(
            engine.get_video_and_chapter_id('https://example.com/video?video_id=42'),
            (None, None),
        )
        self.assertEqual(session.calls, [])

    def test_factory_forwards_channel_specific_arguments(self):
        proxy = {'enabled': False}
        with patch('search.AiGuaEngine') as aigua_engine:
            create_search_engine(AIGUA_CHANNEL, proxy_config=proxy)
            aigua_engine.assert_called_once_with(proxy_config=proxy)

        with patch('search_ncat.NCatSearcher') as ncat_engine:
            create_search_engine(NCAT_CHANNEL, proxy_config=proxy, ncat_cookie='cookie-value')
            ncat_engine.assert_called_once_with(
                proxy_config=proxy,
                cdndefend_js_cookie='cookie-value',
            )

        with patch('search_mofa.MofaSearcher') as mofa_engine:
            create_search_engine(MOFA_CHANNEL, proxy_config=proxy)
            mofa_engine.assert_called_once_with(proxy_config=proxy)

        with patch('search_iyf.IYFSearcher') as iyf_engine:
            create_search_engine(IYF_CHANNEL, proxy_config=proxy, iyf_cookie='full-cookie')
            iyf_engine.assert_called_once_with(proxy_config=proxy, cookie='full-cookie')

    def test_search_adapter_normalizes_engine_signatures(self):
        engine = Mock()
        engine.search.return_value = ['result']

        self.assertEqual(search_with_engine(AIGUA_CHANNEL, engine, '关键词', 1), ['result'])
        engine.search.assert_called_once_with('关键词', 1)

        engine.reset_mock()
        engine.search.return_value = ['result']
        self.assertEqual(search_with_engine(NCAT_CHANNEL, engine, '关键词'), ['result'])
        engine.search.assert_called_once_with('关键词', verbose=False)

        engine.reset_mock()
        engine.search.return_value = ['result']
        self.assertEqual(search_with_engine(IYF_CHANNEL, engine, '关键词'), ['result'])
        engine.search.assert_called_once_with('关键词', verbose=False)


if __name__ == '__main__':
    unittest.main()
