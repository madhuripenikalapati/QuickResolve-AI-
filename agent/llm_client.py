"""Shared LLM client with automatic Groq API key rotation on rate limit."""

import os
import time
import logging
from openai import OpenAI, RateLimitError, BadRequestError, AuthenticationError

logger = logging.getLogger(__name__)

_keys: list[str] = []
_key_index: int = 0

# Cached Gemini credentials object (refreshed automatically by google-auth)
_gemini_credentials = None


def _build_key_pool() -> list[str]:
    primary = os.getenv("GROQ_API_KEY", "")
    extras_raw = os.getenv("GROQ_API_KEYS", "")
    extras = [k.strip() for k in extras_raw.split(",") if k.strip()]
    pool = [primary] + [k for k in extras if k != primary]
    return [k for k in pool if k]


_TIMEOUT = 20  # seconds — fail fast rather than hang forever


def _make_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=_TIMEOUT)


def _get_gemini_token() -> str:
    """Returns a fresh OAuth2 access token from the service account JSON."""
    global _gemini_credentials
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests
    except ImportError as e:
        raise RuntimeError("google-auth not installed. Run: pip install google-auth") from e

    sa_path = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        os.path.join(os.path.dirname(__file__), "..", "gemini_service_account.json"),
    )
    sa_path = os.path.abspath(sa_path)

    if _gemini_credentials is None:
        _gemini_credentials = service_account.Credentials.from_service_account_file(
            sa_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

    if not _gemini_credentials.valid:
        request = google.auth.transport.requests.Request()
        _gemini_credentials.refresh(request)

    return _gemini_credentials.token


def _get_gemini_client() -> OpenAI:
    """Builds an OpenAI-compatible client pointing at Vertex AI Gemini (service account auth)."""
    import json
    sa_path = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        os.path.join(os.path.dirname(__file__), "..", "gemini_service_account.json"),
    )
    sa_path = os.path.abspath(sa_path)
    with open(sa_path) as f:
        sa = json.load(f)
    project = sa["project_id"]
    location = os.getenv("GEMINI_LOCATION", "us-central1")

    return OpenAI(
        api_key=_get_gemini_token(),
        base_url=f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}/locations/{location}/endpoints/openapi/",
        timeout=_TIMEOUT,
    )


def _ensure_pool():
    global _keys
    if not _keys:
        _keys = _build_key_pool()


def get_client() -> OpenAI:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "gemini":
        return _get_gemini_client()
    _ensure_pool()
    if provider != "groq":
        return OpenAI()
    return _make_client(_keys[_key_index % len(_keys)])


def chat_with_rotation(**kwargs) -> object:
    """
    Drop-in replacement for client.chat.completions.create(**kwargs).
    For Groq: rotates to the next key on 429 and retries, cycling through all keys once.
    For Gemini: refreshes service account token and calls the Gemini OpenAI-compatible endpoint.
    """
    global _key_index

    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "gemini":
        client = _get_gemini_client()
        return client.chat.completions.create(**kwargs)

    if provider != "groq":
        return OpenAI().chat.completions.create(**kwargs)

    _ensure_pool()
    num_keys = len(_keys)
    if not num_keys:
        raise RuntimeError("No Groq API keys configured. Set GROQ_API_KEY in .env")
    last_error = None

    for attempt in range(num_keys * 2):  # two full cycles with a pause between
        key = _keys[_key_index % num_keys]
        client = _make_client(key)
        try:
            result = client.chat.completions.create(**kwargs)
            _key_index += 1  # round-robin: rotate after every successful call
            return result
        except RateLimitError as e:
            last_error = e
            logger.warning(f"Rate limit on key index {_key_index % num_keys}, rotating.")
            _key_index += 1
            if attempt == num_keys - 1:  # exhausted all keys once — wait before retry cycle
                time.sleep(5)
        except (BadRequestError, AuthenticationError) as e:
            last_error = e
            logger.warning(f"Key index {_key_index % num_keys} rejected ({type(e).__name__}), rotating.")
            _key_index += 1

    raise last_error


def chat_stream_with_rotation(**kwargs):
    """Streaming version of chat_with_rotation. Returns a Groq stream object."""
    global _key_index

    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider != "groq":
        raise RuntimeError("Streaming only supported for Groq provider")

    _ensure_pool()
    num_keys = len(_keys)
    if not num_keys:
        raise RuntimeError("No Groq API keys configured.")
    last_error = None

    for attempt in range(num_keys * 2):
        key = _keys[_key_index % num_keys]
        client = _make_client(key)
        try:
            stream = client.chat.completions.create(stream=True, **kwargs)
            _key_index += 1  # round-robin: rotate after every successful call
            return stream
        except RateLimitError as e:
            last_error = e
            logger.warning(f"Rate limit on key index {_key_index % num_keys}, rotating.")
            _key_index += 1
            if attempt == num_keys - 1:
                time.sleep(5)
        except (BadRequestError, AuthenticationError) as e:
            last_error = e
            logger.warning(f"Key index {_key_index % num_keys} rejected ({type(e).__name__}), rotating.")
            _key_index += 1

    raise last_error


def get_model() -> str:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "gemini":
        # Vertex AI OpenAI-compat endpoint requires "google/" prefix
        return os.getenv("GEMINI_MODEL", "google/gemini-2.0-flash-001")
    if provider == "groq":
        return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    return os.getenv("OPENAI_MODEL", "gpt-4o")


def get_classify_model() -> str:
    """Lightweight model for classify — uses a separate Groq quota pool."""
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "groq":
        return os.getenv("GROQ_CLASSIFY_MODEL", "llama-3.1-8b-instant")
    return get_model()
