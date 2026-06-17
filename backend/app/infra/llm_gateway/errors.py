from __future__ import annotations


class LLMGatewayError(Exception):
    pass


class LLMProviderUnavailable(LLMGatewayError):
    pass


class LLMProviderError(LLMGatewayError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message
