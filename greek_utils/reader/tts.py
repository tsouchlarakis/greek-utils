"""
Native-speaker audio for a reading text, through a cloud text-to-speech provider.

Two providers, both called over plain HTTPS with the key passed in by the caller (this
package never reads a key from disk or from a fixed environment variable):

- Azure AI Speech neural voices (``el-GR-AthinaNeural``, ``el-GR-NestorasNeural``)
  through the REST endpoint, with an optional SSML speaking rate.
- ElevenLabs (Multilingual v2) with any voice id the caller names.

Neither result carries word timings. A caller that needs them (sentence highlighting,
per-word native clips) transcribes the audio with word timestamps and aligns that to the
text with ``greek_utils.reader.compare``, which works the same for every provider, and
``word_timings`` below turns that alignment into a list of spans.
"""

from collections.abc import Callable
from dataclasses import dataclass
from xml.sax.saxutils import escape

import requests

AZURE = 'azure'
ELEVENLABS = 'elevenlabs'
PROVIDERS = (AZURE, ELEVENLABS)

AZURE_VOICES = ('el-GR-AthinaNeural', 'el-GR-NestorasNeural')
AZURE_FORMAT = 'audio-24khz-96kbitrate-mono-mp3'
ELEVENLABS_MODEL = 'eleven_multilingual_v2'
ELEVENLABS_FORMAT = 'mp3_44100_128'
MP3 = 'audio/mpeg'
USER_AGENT = 'greek-utils-reader'
TIMEOUT_S = 60
MAX_CHARS = 5000  # a reading text is ~1,000 characters; anything near this is a mistake

Post = Callable[..., requests.Response]


class TTSError(RuntimeError):
    """A provider refused or failed. ``code`` is safe to log; the message may not be."""

    def __init__(self, code: str, message: str = ''):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class Synthesis:
    audio: bytes
    mime: str
    provider: str
    voice: str

    def to_dict(self) -> dict:
        return {'mime': self.mime, 'provider': self.provider, 'voice': self.voice, 'bytes': len(self.audio)}


def azure_ssml(text: str, voice: str, rate: str | None = None) -> str:
    body = escape(text)
    if rate:
        body = f"<prosody rate='{escape(rate)}'>{body}</prosody>"
    return (f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='el-GR'>"
            f"<voice name='{escape(voice)}'>{body}</voice></speak>")


def _check(text: str, key: str) -> None:
    if not key:
        raise TTSError('no_key')
    if not text.strip():
        raise TTSError('empty_text')
    if len(text) > MAX_CHARS:
        raise TTSError('text_too_long')


def _response(resp: requests.Response, provider: str) -> bytes:
    if resp.status_code in (401, 403):
        raise TTSError(f'{provider}_unauthorized')
    if resp.status_code == 429:
        raise TTSError(f'{provider}_rate_limited')
    if resp.status_code >= 400:
        raise TTSError(f'{provider}_http_{resp.status_code}')
    if not resp.content:
        raise TTSError(f'{provider}_empty_audio')
    return resp.content


def azure(text: str, *, key: str, region: str, voice: str = AZURE_VOICES[0], rate: str | None = None,
          post: Post = requests.post) -> Synthesis:
    _check(text, key)
    if not region:
        raise TTSError('no_region')
    try:
        resp = post(
            f'https://{region}.tts.speech.microsoft.com/cognitiveservices/v1',
            data=azure_ssml(text, voice, rate).encode('utf-8'),
            headers={
                'Ocp-Apim-Subscription-Key': key,
                'Content-Type': 'application/ssml+xml',
                'X-Microsoft-OutputFormat': AZURE_FORMAT,
                'User-Agent': USER_AGENT,
            },
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise TTSError('azure_unreachable') from exc
    return Synthesis(_response(resp, AZURE), MP3, AZURE, voice)


def elevenlabs(text: str, *, key: str, voice: str, model: str = ELEVENLABS_MODEL,
               post: Post = requests.post) -> Synthesis:
    _check(text, key)
    if not voice:
        raise TTSError('no_voice')
    try:
        resp = post(
            f'https://api.elevenlabs.io/v1/text-to-speech/{voice}',
            params={'output_format': ELEVENLABS_FORMAT},
            json={'text': text, 'model_id': model, 'language_code': 'el'},
            headers={'xi-api-key': key, 'Accept': MP3, 'User-Agent': USER_AGENT},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise TTSError('elevenlabs_unreachable') from exc
    return Synthesis(_response(resp, ELEVENLABS), MP3, ELEVENLABS, voice)


def synthesize(provider: str, text: str, *, key: str, voice: str, region: str | None = None,
               rate: str | None = None, post: Post = requests.post) -> Synthesis:
    if provider == AZURE:
        return azure(text, key=key, region=region or '', voice=voice, rate=rate, post=post)
    if provider == ELEVENLABS:
        return elevenlabs(text, key=key, voice=voice, post=post)
    raise TTSError('unknown_provider')


def word_timings(comparison) -> list[dict]:
    """
    Per text word, the span the native audio speaks it in, from a ``compare`` of the
    text against a timed transcript of that audio. Words the transcript did not
    match get no span (``start``/``end`` None) rather than an interpolated guess.
    """
    out = []
    for w in comparison.words:
        matched = w.status in ('clean', 'stress', 'unclear', 'misread')
        out.append({
            'index': w.index,
            'start': w.start if matched else None,
            'end': w.end if matched else None,
        })
    return out
