import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class GeminiAPI:
    def __init__(self):
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        self.models = {
            'summarize': genai.GenerativeModel(os.getenv('GEMINI_MODEL_SUMMARIZE')),
            'date_extract': genai.GenerativeModel(os.getenv('GEMINI_MODEL_DATE_EXTRACT'))
        }
    
    async def generate_content(self, model_key: str, prompt: str, **kwargs) -> str:
        """Generic content generation method for Gemini"""
        try:
            print(f"Generating content with model: {model_key}") if os.getenv('DEBUG') == 'true' else None
            response = await self.models[model_key].generate_content_async(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=kwargs.get('temperature', 0.2),
                    max_output_tokens=kwargs.get('max_tokens')
                )
            )
            print(f"Response: {response.text}") if os.getenv('DEBUG') == 'true' else None
            return response.text
        except Exception as e:
            print(f"Gemini API error: {str(e)}")
            raise e