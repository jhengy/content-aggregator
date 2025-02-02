from typing import Dict, Optional
import os
import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core.exceptions import ResourceExhausted
from .exceptions import RateLimitExceededError
from urllib3.util import Retry


load_dotenv()

class GeminiAPI:
    RETRY_AFTER_DEFAULT = 15
    
    """Client for interacting with Gemini API with model management"""
    def __init__(self):
        self._validate_env_vars()
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.models: Dict[str, genai.GenerativeModel] = {
            'summarize': genai.GenerativeModel(os.getenv('GEMINI_MODEL_SUMMARIZE')),
            'date_extract': genai.GenerativeModel(os.getenv('GEMINI_MODEL_DATE_EXTRACT'))
        }
    
    async def generate_content(
        self, 
        model_key: str, 
        prompt: str, 
        temperature: float = 0.2,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate content asynchronously with specified model and parameters"""
        try:
            self._log_debug(f"Generating content with model: {model_key}")
            response = await self.models[model_key].generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens
                )
            )
            self._log_debug(f"Response: {response.text}")
            return response.text
        except ResourceExhausted as e:
            retry_after = self._parse_retry_after(e.retry_after) if hasattr(e, 'retry_after') else self.RETRY_AFTER_DEFAULT
            raise RateLimitExceededError(retry_after=retry_after) from e
        except Exception as e:
            print(f"Gemini API error: {str(e)}")
            
            if hasattr(e, 'status_code') and e.status_code == 429:
                retry_after = self._parse_retry_after(e.headers.get('Retry-After')) if hasattr(e, 'headers') else self.RETRY_AFTER_DEFAULT
                raise RateLimitExceededError(retry_after=retry_after) from e
            raise e

    def _log_debug(self, message: str) -> None:
        """Helper for debug logging"""
        if os.getenv('DEBUG') == 'true':
            print(message)

    def _parse_retry_after(self, retry_after_str):
        try:
            return Retry.parse_retry_after(retry_after_str)
        except Exception as e:
            print(f"Error parsing {retry_after_str} - {str(e)}")
            return self.RETRY_AFTER_DEFAULT

    def _validate_env_vars(self):
        """Validate required environment variables"""
        required_vars = [
            'GEMINI_API_KEY',
            'GEMINI_MODEL_SUMMARIZE',
            'GEMINI_MODEL_DATE_EXTRACT'
        ]
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(
                f"Missing required Gemini API environment variables: {', '.join(missing)}. "
                "Please check your .env configuration."
            )
