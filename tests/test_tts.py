import pytest
import requests

from greek_utils.reader import tts
from greek_utils.reader.compare import compare


class FakeResponse:
    def __init__(self, status=200, content=b'ID3fake'):
        self.status_code = status
        self.content = content


class Recorder:
    def __init__(self, response=None, raises=None):
        self.calls = []
        self.response = response or FakeResponse()
        self.raises = raises

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.raises:
            raise self.raises
        return self.response


def test_azure_request_shape_and_escaping():
    post = Recorder()
    out = tts.azure('Ο Γιάννης & η «Μαρία» <ήρθαν>.', key='k', region='westeurope',
                    voice='el-GR-NestorasNeural', rate='-10%', post=post)
    url, kw = post.calls[0]
    assert url == 'https://westeurope.tts.speech.microsoft.com/cognitiveservices/v1'
    body = kw['data'].decode('utf-8')
    assert "xml:lang='el-GR'" in body and "name='el-GR-NestorasNeural'" in body
    assert '&amp; η «Μαρία» &lt;ήρθαν&gt;.' in body
    assert "<prosody rate='-10%'>" in body
    assert kw['headers']['Ocp-Apim-Subscription-Key'] == 'k'
    assert kw['headers']['X-Microsoft-OutputFormat'] == tts.AZURE_FORMAT
    assert out.audio == b'ID3fake' and out.mime == tts.MP3 and out.provider == tts.AZURE


def test_elevenlabs_request_shape():
    post = Recorder()
    out = tts.elevenlabs('Καλημέρα.', key='k', voice='v123', post=post)
    url, kw = post.calls[0]
    assert url == 'https://api.elevenlabs.io/v1/text-to-speech/v123'
    assert kw['json'] == {'text': 'Καλημέρα.', 'model_id': tts.ELEVENLABS_MODEL, 'language_code': 'el'}
    assert kw['headers']['xi-api-key'] == 'k'
    assert out.voice == 'v123' and out.provider == tts.ELEVENLABS


@pytest.mark.parametrize('status,code', [(401, 'azure_unauthorized'), (429, 'azure_rate_limited'),
                                         (500, 'azure_http_500')])
def test_errors_carry_safe_codes(status, code):
    with pytest.raises(tts.TTSError) as err:
        tts.azure('Καλημέρα.', key='secret-key', region='r', post=Recorder(FakeResponse(status)))
    assert err.value.code == code
    assert 'secret-key' not in str(err.value)


def test_empty_audio_and_network_failure():
    with pytest.raises(tts.TTSError) as err:
        tts.elevenlabs('Καλημέρα.', key='k', voice='v', post=Recorder(FakeResponse(200, b'')))
    assert err.value.code == 'elevenlabs_empty_audio'
    with pytest.raises(tts.TTSError) as err:
        tts.azure('Καλημέρα.', key='k', region='r', post=Recorder(raises=requests.ConnectionError('x')))
    assert err.value.code == 'azure_unreachable'


@pytest.mark.parametrize('kwargs,code', [
    ({'text': 'x', 'key': ''}, 'no_key'),
    ({'text': '  ', 'key': 'k'}, 'empty_text'),
    ({'text': 'α' * (tts.MAX_CHARS + 1), 'key': 'k'}, 'text_too_long'),
])
def test_refuses_before_calling(kwargs, code):
    post = Recorder()
    with pytest.raises(tts.TTSError) as err:
        tts.azure(region='r', post=post, **kwargs)
    assert err.value.code == code
    assert post.calls == []


def test_synthesize_dispatch():
    post = Recorder()
    assert tts.synthesize('azure', 'Γεια.', key='k', voice='el-GR-AthinaNeural', region='r', post=post).provider == 'azure'
    assert tts.synthesize('elevenlabs', 'Γεια.', key='k', voice='v', post=post).provider == 'elevenlabs'
    with pytest.raises(tts.TTSError):
        tts.synthesize('other', 'Γεια.', key='k', voice='v', post=post)


def test_word_timings_from_alignment():
    text = 'Ο Γιάννης ήρθε σπίτι.'
    heard = [
        {'word': 'Ο', 'start': 0.0, 'end': 0.2},
        {'word': 'Γιάννης', 'start': 0.2, 'end': 0.7},
        {'word': 'σπίτι', 'start': 1.0, 'end': 1.4},
    ]
    timings = tts.word_timings(compare(text, heard))
    assert [t['index'] for t in timings] == [0, 1, 2, 3]
    assert timings[1] == {'index': 1, 'start': 0.2, 'end': 0.7}
    assert timings[2] == {'index': 2, 'start': None, 'end': None}  # skipped: no guessed span
    assert timings[3]['start'] == 1.0
