from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from evalbench.datasets import EvaluationExample, ScorerSpec
from evalbench.providers import (
    OpenAIProvider,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderTransientError,
)


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, responses):
        self.responses = responses


def _example():
    return EvaluationExample(
        id="provider-test",
        input={"question": "Where is Normandy?"},
        mock_response="France",
        scorers=[ScorerSpec(type="exact_match", expected="France")],
    )


def test_openai_provider_uses_responses_api_and_captures_usage():
    api_response = SimpleNamespace(
        id="resp_test",
        model="gpt-test",
        output_text=" France ",
        usage=SimpleNamespace(input_tokens=12, output_tokens=2, total_tokens=14),
    )
    responses = FakeResponses(response=api_response)
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        max_output_tokens=64,
        client=FakeClient(responses),
    )

    result = provider.generate("Rendered prompt", _example())

    assert result.text == "France"
    assert provider.name == "openai:gpt-test:max64"
    assert responses.requests == [
        {
            "model": "gpt-test",
            "input": "Rendered prompt",
            "max_output_tokens": 64,
            "store": False,
        }
    ]
    assert result.metadata == {
        "response_id": "resp_test",
        "model": "gpt-test",
        "input_tokens": 12,
        "output_tokens": 2,
        "total_tokens": 14,
        "stored": False,
    }


def test_openai_provider_rejects_missing_key():
    with pytest.raises(ProviderConfigurationError, match="OPENAI_API_KEY"):
        OpenAIProvider(api_key=" ", model="gpt-test")


def test_openai_provider_rejects_empty_text_response():
    api_response = SimpleNamespace(
        id="resp_empty",
        model="gpt-test",
        output_text="  ",
        usage=None,
    )
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        client=FakeClient(FakeResponses(response=api_response)),
    )

    with pytest.raises(ProviderResponseError, match="no text output"):
        provider.generate("Rendered prompt", _example())


def test_openai_provider_classifies_timeout_as_transient():
    timeout = APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    provider = OpenAIProvider(
        api_key="test-key",
        model="gpt-test",
        client=FakeClient(FakeResponses(error=timeout)),
    )

    with pytest.raises(ProviderTransientError, match="connection failed"):
        provider.generate("Rendered prompt", _example())
