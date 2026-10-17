"""Thin wrapper around the Anthropic Python SDK (optional extra ``ai``; imported lazily).

One request per call: a system prompt and the operator's text in, one JSON object out. The reply is constrained by
structured outputs (``output_config.format`` with a JSON schema) to the schema the caller passes. Claude Opus 5.5 rejects
forced ``tool_choice``, so structured outputs, not a forced tool call, carries the constraint. This module knows nothing
about the bench: benchsim.ai.pipeline builds the prompt and the schema and checks the reply again, because the API
constraint is not the gate.

    BENCHSIM_LLM_MODEL   model id (default claude-opus-5-5)
    ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN   credentials. ``available()`` looks only at these two variables, so an
                         ``ant auth login`` profile is not probed (no surprise network call); set a key to use the LLM.

Refusal fallback: for the models that accept it, requests carry ``fallbacks="default"`` (beta
server-side-fallback-2026-07-01), so a classifier decline is retried server-side on the model Anthropic recommends.
"""
import os

DEFAULT_MODEL = 'claude-opus-5-5'
MAX_TOKENS = 16000                    # ceiling for a non-streaming request; a plan is ~2k tokens
EFFORT = 'medium'                     # Opus 5.5's default, set explicitly
TIMEOUT_S = 120.0
MAX_RETRIES = 1
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
FALLBACK_MODELS = ('claude-opus-5-5', 'claude-opus-5', 'claude-fable-5-1', 'claude-sonnet-5-5')   # accept fallbacks="default"


class LLMUnavailable(RuntimeError):
    """the model could not produce a reply (no SDK, no credentials, network or API error, refusal, truncation)"""


def model_id():
    return os.environ.get('BENCHSIM_LLM_MODEL') or DEFAULT_MODEL


def available():
    """-> (ok, reason). Checks that the SDK imports and a key or token is set; sends nothing."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, 'anthropic SDK not installed (uv pip install -e ".[ai]")'
    if not (os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('ANTHROPIC_AUTH_TOKEN')):
        return False, 'no ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN in the environment'
    return True, ''


class AnthropicLLM:
    """``complete_json(system, user, schema) -> str`` (the JSON text of the reply). ``client``: an injected SDK client
    (tests pass a fake); by default ``anthropic.Anthropic()`` is created on first use. ``last`` holds the model, request id,
    stop reason and token usage of the latest reply."""

    def __init__(self, model=None, client=None, timeout_s=TIMEOUT_S):
        self.model = model or model_id(); self._client = client; self.timeout_s = timeout_s; self.last = None

    def client(self):
        if self._client is None:
            ok, why = available()
            if not ok: raise LLMUnavailable(why)
            import anthropic
            self._client = anthropic.Anthropic(timeout=self.timeout_s, max_retries=MAX_RETRIES)
        return self._client

    def request(self, system, user, schema):
        """keyword arguments of the Messages API call"""
        kw = dict(model=self.model, max_tokens=MAX_TOKENS, system=system, messages=[dict(role='user', content=user)],
                  output_config=dict(effort=EFFORT, format=dict(type='json_schema', schema=schema)))
        if self.model in FALLBACK_MODELS: kw.update(betas=[FALLBACK_BETA], fallbacks='default')
        return kw

    def complete_json(self, system, user, schema):
        c = self.client(); kw = self.request(system, user, schema)
        create = c.beta.messages.create if 'betas' in kw else c.messages.create
        try:
            r = create(**kw)
        except Exception as e:
            raise LLMUnavailable(_describe(e)) from e
        self.last = dict(model=getattr(r, 'model', self.model), request_id=getattr(r, '_request_id', None), stop_reason=r.stop_reason,
                         usage=dict(input_tokens=getattr(r.usage, 'input_tokens', None), output_tokens=getattr(r.usage, 'output_tokens', None))
                         if getattr(r, 'usage', None) is not None else None)
        if r.stop_reason == 'refusal':
            sd = getattr(r, 'stop_details', None)
            raise LLMUnavailable('model declined (category %s)' % (getattr(sd, 'category', None) if sd else None))
        if r.stop_reason == 'max_tokens': raise LLMUnavailable('reply truncated at max_tokens')
        text = ''.join(b.text for b in r.content if getattr(b, 'type', None) == 'text')
        if not text: raise LLMUnavailable('reply has no text block (stop_reason %s)' % r.stop_reason)
        return text


def _describe(e):
    """SDK exception -> short reason, most specific first (the SDK is imported only if it is installed)"""
    try:
        import anthropic
    except ImportError:
        return '%s: %s' % (type(e).__name__, e)
    if isinstance(e, anthropic.AuthenticationError): return 'authentication failed (check ANTHROPIC_API_KEY)'
    if isinstance(e, anthropic.PermissionDeniedError): return 'API key lacks permission'
    if isinstance(e, anthropic.NotFoundError): return 'model or endpoint not found (BENCHSIM_LLM_MODEL?)'
    if isinstance(e, anthropic.RateLimitError): return 'rate limited'
    if isinstance(e, anthropic.BadRequestError): return 'bad request: %s' % getattr(e, 'message', e)
    if isinstance(e, anthropic.APIStatusError): return 'API error %s' % e.status_code
    if isinstance(e, anthropic.APITimeoutError): return 'request timed out'
    if isinstance(e, anthropic.APIConnectionError): return 'network unavailable'
    return '%s: %s' % (type(e).__name__, e)
