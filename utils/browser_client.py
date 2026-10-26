"""Small OpenAI-compatible client using Stlite's browser HTTP transport.

No SDK native wheels, socket transport, background threads or stored credentials.
Browser CORS policy applies. Streaming responses are displayed as one completed chunk.
"""
from types import SimpleNamespace
import requests


class BrowserNetworkError(RuntimeError):
    """The browser could not reach the provider, including CORS failures."""


class BrowserAPIError(RuntimeError):
    """A provider returned an unsuccessful response; never expose its body."""


class OpenAI:
    def __init__(self, api_key, base_url):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, stream=False, extra_body=None, **options):
        payload = dict(options, model=model, messages=messages, stream=False)
        if extra_body:
            payload.update(extra_body)
        try:
            response = requests.post(
                self._base_url + "/chat/completions",
                headers={"Authorization": "Bearer " + self._api_key},
                json=payload,
                timeout=120,
            )
        except Exception:
            raise BrowserNetworkError("Check network access and the provider's CORS policy.") from None
        if not response.ok:
            raise BrowserAPIError(f"Provider returned HTTP {response.status_code}.") from None
        try:
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("Expected text completion")
        except (KeyError, IndexError, TypeError, ValueError):
            raise BrowserAPIError("Provider returned an unsupported response format.") from None
        if stream:
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
