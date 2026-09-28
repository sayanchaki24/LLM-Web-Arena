from app.providers.base import BaseProvider
from app.providers.chatgpt import ChatGPTProvider
from app.providers.claude import ClaudeProvider
from app.providers.gemini import GeminiProvider
from app.providers.glm import GLMProvider

PROVIDERS = {
    "ChatGPT": ChatGPTProvider(),
    "Claude": ClaudeProvider(),
    "Gemini": GeminiProvider(),
    "GLM": GLMProvider(),
}

__all__ = ["BaseProvider", "ChatGPTProvider", "ClaudeProvider", "GeminiProvider", "GLMProvider", "PROVIDERS"]
