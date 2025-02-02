from typing import Dict, Optional
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class GeminiAPI:
    """Client for interacting with Gemini API with model management"""
    def __init__(self):
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
        except Exception as e:
            print(f"Gemini API error: {str(e)}")
            raise e

    def _log_debug(self, message: str) -> None:
        """Helper for debug logging"""
        if os.getenv('DEBUG') == 'true':
            print(message)