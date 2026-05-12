"""
LLM client for Llama 3.3 70B Versatile via Groq API.
Handles prompt construction and structured JSON output parsing.
"""
import json
import os
import re
from typing import Optional

from groq import Groq


MODEL_NAME = "llama-3.3-70b-versatile"


class LLMClient:
    """Wrapper around Groq's Llama 3.3 70B Versatile."""

    def __init__(self, model: str = MODEL_NAME):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Get a key at https://console.groq.com/keys and export it: "
                "`export GROQ_API_KEY=<your-key>` (locally) or set it in the "
                "Render dashboard (production)."
            )
        self.model = model
        self.client = Groq(api_key=api_key)

    def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> str:
        """
        Send a prompt to the LLM and return the text response.

        Args:
            prompt: User message.
            system: Optional system prompt.
            temperature: Sampling temperature (0.0-1.0). Lower = more deterministic.
            json_mode: If True, request JSON output (Groq's response_format=json_object).

        Returns:
            The LLM's response as a string.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def chat_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.1,
    ) -> dict:
        """
        Send a prompt and parse the response as JSON.

        Uses Groq's native JSON mode for reliability.
        Falls back to regex extraction if direct parsing fails.

        Returns:
            Parsed JSON as a dict.

        Raises:
            ValueError: If response cannot be parsed as JSON.
        """
        raw = self.chat(prompt, system=system, temperature=temperature, json_mode=True)

        # Try direct parse first
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Fallback: extract JSON object from text using regex
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse JSON from LLM response: {e}\nRaw: {raw[:500]}")

        raise ValueError(f"No JSON found in LLM response. Raw: {raw[:500]}")


# ============================================================
# Singleton instance for easy import
# ============================================================
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get the global LLM client instance (lazy init)."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


# ============================================================
# Quick test
# ============================================================
if __name__ == "__main__":
    client = get_llm_client()

    print("Test 1: plain chat")
    response = client.chat("Say hello in 5 words.")
    print(f"Response: {response}\n")

    print("Test 2: JSON mode")
    response = client.chat_json(
        prompt='Return a JSON object with two fields: "greeting" (string) and "score" (integer 0-100).'
    )
    print(f"Parsed JSON: {response}")
    print(f"Type: {type(response)}")
