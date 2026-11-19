import os
from google import genai
from google.genai import types

# 1. Set your API key here or via the GEMINI_API_KEY environment variable
API_KEY = "AQ.Ab8RN6K-zAZMCUPkZRjs3vdbVQgejGKSwWOgY-Sv7wo8p-P8yw"
# os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")

# 2. Initialize the official client
client = genai.Client(api_key=API_KEY)


def ask_gemini(prompt: str, system_prompt: str | None = None, model: str = "gemini-3.5-flash-lite") -> str:
    config = types.GenerateContentConfig(
        temperature=0.3,
        system_instruction=system_prompt,
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return response.text


if __name__ == "__main__":
    # First, list the exact models enabled for your API key so there is zero guesswork
    print("Available models for your API key:")
    for m in client.models.list():
        if "generateContent" in (m.supported_actions or []):
            print(" -", m.name)

    print("\n--- Sending test prompt ---")
    answer = ask_gemini(
        prompt="Explain how software impact analysis helps enterprise teams in 3 concise bullet points.",
        system_prompt="You are a concise, expert technical assistant.",
        model="gemini-3.5-flash-lite",  # Or pick any model name printed in the list above
    )
    print(answer)