"""DeepEval judge backed by the same free Gemini key."""
from deepeval.models import DeepEvalBaseLLM

from src import llm, settings


class GeminiJudge(DeepEvalBaseLLM):
    def __init__(self):
        self.model_name = settings.GEMINI_MODEL

    def load_model(self):
        return self

    def generate(self, prompt: str, schema=None):
        if schema is not None:
            data = llm.extract_json(llm.generate(prompt + "\nReturn ONLY valid JSON.", json_mode=True, temperature=0))
            return schema(**data)
        return llm.generate(prompt, temperature=0)

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)

    def get_model_name(self):
        return self.model_name
