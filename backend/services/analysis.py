import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List
from core.config import settings

class VideoReportSchema(BaseModel):
    overall_sentiment: str = Field(description="A short phrase representing the overall sentiment (e.g., 'Mostly Positive', 'Highly Critical').")
    summary: str = Field(description="A 2-3 sentence overview of the audience's reaction.")
    top_complaints: str = Field(description="An HTML unordered list (<ul><li>...</li></ul>) of the top 3 complaints.")
    top_praises: str = Field(description="An HTML unordered list (<ul><li>...</li></ul>) of the top 3 praises.")

class VideoReportService:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_id = 'gemini-3.1-flash'

    def generate_report(self, pos_count: int, neg_count: int, neu_count: int, pos_texts: List[str], neg_texts: List[str]) -> dict:
        """
        Generates a comprehensive executive summary based on the IndoBERT pre-processed data.
        """
        prompt = f"""
You are a Consumer Insights Analyst. I have processed YouTube comments using an IndoBERT NLP model.
Stats: {pos_count} Positive, {neg_count} Negative, {neu_count} Neutral.

Here is a sample of the negative comments:
{json.dumps(neg_texts, ensure_ascii=False)}

Here is a sample of the positive comments:
{json.dumps(pos_texts, ensure_ascii=False)}

Create a structured executive summary based on these comments.
Format `top_complaints` and `top_praises` as raw HTML unordered lists (<ul><li>Item 1</li><li>Item 2</li></ul>) so it can be rendered directly in a web UI.

You MUST return the output as a valid JSON object strictly matching this format:
{{
    "overall_sentiment": "A short phrase (e.g. Mostly Positive)",
    "summary": "A 2-3 sentence overview...",
    "top_complaints": "<ul><li>...</li></ul>",
    "top_praises": "<ul><li>...</li></ul>"
}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )
            if response.text:
                return json.loads(response.text)
            return {}
        except Exception as e:
            print(f"Error generating video report: {e}")
            return {}
