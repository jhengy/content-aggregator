import os
import openai
from typing import Dict, Optional
from dotenv import load_dotenv


load_dotenv()


class OpenAIClient:
    VALID_MODEL_KEYS = ['summarize_post', 'summarize_all', 'date_extract']
    
    def __init__(self):
        self._validate_env_vars()
        self.client = openai.AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )
        self.models = self._load_models()
        print(f"OpenAIClient#self.models: {str(self.models)}")
    
    def _load_models(self) -> Dict[str, str]:
        default_model = os.getenv("OPENAI_MODEL", "")
        return {
            key: os.getenv(f"OPENAI_MODEL_{key.upper()}", default_model)
            for key in self.VALID_MODEL_KEYS
        }
    
    def _validate_env_vars(self) -> None:
        missing = []
        
        if not os.getenv("OPENAI_API_KEY"):
            missing.append("OPENAI_API_KEY")
        
        base_url = os.getenv("OPENAI_BASE_URL", "")
        if not base_url:
            missing.append("OPENAI_BASE_URL")
        
        for key in self.VALID_MODEL_KEYS:
            if not os.getenv(f"OPENAI_MODEL_{key.upper()}"):
                missing.append(f"OPENAI_MODEL_{key.upper()}")
                break
        
        if missing:
            raise ValueError(
                f"Missing required OpenAI-compatible API environment variables: {', '.join(set(missing))}. "
                "Please check your .env configuration."
            )
    
    async def generate_content(
        self,
        model_key: str,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None
    ) -> str:
        if model_key not in self.models:
            raise ValueError(f"Invalid model_key: {model_key}. Valid keys: {self.VALID_MODEL_KEYS}")
        
        model = self.models[model_key]
        if not model:
            raise ValueError(f"No model configured for {model_key}")
        
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"OpenAI-compatible API error: {str(e)}")
            raise
