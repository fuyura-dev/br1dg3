from google import genai

from app.config import settings

client = genai.Client(api_key=settings.LLM_API_KEY)

stream = client.interactions.create(
    model=settings.LLM_MODEL,
    input="Explain how AI works",
    stream=True
)


for event in stream:
    print(event)