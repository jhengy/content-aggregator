import os
import openai
from typing import Dict, Optional
from dotenv import load_dotenv
from .exceptions import RateLimitExceededError


load_dotenv()


class OpenAIClient:
    VALID_MODEL_KEYS = ['summarize_post', 'summarize_all', 'date_extract']
    RETRY_AFTER_DEFAULT = 15
    
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
            content = response.choices[0].message.content
            return content if content is not None else ""
        except openai.RateLimitError as e:
            retry_after = self._parse_retry_after(
                e.response.headers.get('Retry-After')
            ) if hasattr(e, 'response') and e.response else self.RETRY_AFTER_DEFAULT
            raise RateLimitExceededError(retry_after=retry_after) from e
        except Exception as e:
            if getattr(e, 'status_code', None) == 429:
                retry_after = self._parse_retry_after(
                    getattr(e, 'headers', {}).get('Retry-After')
                )
                raise RateLimitExceededError(retry_after=retry_after) from e
            print(f"OpenAI-compatible API error: {str(e)}")
            raise

    def _parse_retry_after(self, retry_after_str: Optional[str]) -> int:
        if retry_after_str is None:
            return self.RETRY_AFTER_DEFAULT
        try:
            return int(retry_after_str)
        except (ValueError, TypeError):
            return self.RETRY_AFTER_DEFAULT
