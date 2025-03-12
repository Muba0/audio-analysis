import os
import logging
import google.generativeai as genai
import asyncio
import traceback
from typing import Optional, Dict, Any
from google.generativeai.types import GenerationConfig, HarmCategory, HarmBlockThreshold

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

async def validate_api_key(api_key: str) -> bool:
    """
    Validate the Google Generative AI API key
    """
    if not api_key or api_key == 'YOUR_API_KEY':
        logger.error("Invalid API key provided")
        return False
    
    try:
        genai.configure(api_key=api_key)
        # Try a simple test to verify key works
        model = genai.GenerativeModel('gemini-1.5-flash')
        model.generate_content("Test")
        return True
    except Exception as e:
        logger.error(f"API key validation failed: {e}")
        return False

async def transcribe_audio(
    media_path: str,
    api_key: str,
    context: Optional[str] = None,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Transcribe and analyze audio file using Google Generative AI
    """
    # Validate API key first
    if not validate_api_key(api_key):
        return {
            'success': False,
            'error': 'Invalid or unauthorized API key',
            'context': context,
            'details': 'API key validation failed'
        }

    for attempt in range(max_retries):
        try:
            logger.info(f"Transcription attempt {attempt + 1}")

            # Validate file existence and readability
            if not os.path.exists(media_path):
                raise FileNotFoundError(f"Audio file not found: {media_path}")
            
            if os.path.getsize(media_path) == 0:
                raise ValueError(f"Audio file is empty: {media_path}")

            # Upload the audio file using the new files API
            audio_file = genai.upload_file(media_path)
            logger.info(f"File uploaded successfully: {audio_file}")

            # Configure safety settings to be less restrictive
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE
            }

            # Use the Gemini 1.5 Flash model which supports multimodal input
            model = genai.GenerativeModel(
                'gemini-2.0-flash',
                generation_config=GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=1280000
                ),
                safety_settings=safety_settings
            )

            # Read the prompt from file
            with open("prompt_1.txt", "r", encoding="utf-8") as file:
                prompt_1_content = file.read()

            # Prepare the prompt
            prompt = f"""
            Context: {context or 'General conversation analysis'}

            {prompt_1_content}
            """

            # Generate content with the audio file using the new API
            response = model.generate_content([audio_file, prompt])

            # Process the response
            if response and response.text:
                return {
                    'success': True,
                    'transcription': response.text,
                    'context': context or 'General conversation',
                    'details': 'Transcription completed successfully'
                }
            else:
                logger.error("No transcription generated")
                raise ValueError("Failed to generate transcription")

        except Exception as e:
            logger.error(f"Audio transcription error on attempt {attempt + 1}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            if attempt == max_retries - 1:
                return {
                    'success': False,
                    'error': str(e),
                    'context': context,
                    'details': traceback.format_exc()
                }

            # Wait before retrying
            await asyncio.sleep(2 ** attempt)

    return {
        'success': False,
        'error': 'Maximum retries exceeded',
        'context': context,
        'details': 'Failed to transcribe audio after multiple attempts'
    }

async def cleanup_file(media_path: str):
    """
    Clean up the media file after processing.
    """
    try:
        if os.path.exists(media_path):
            os.remove(media_path)
            logger.info(f"Successfully removed file: {media_path}")
    except Exception as e:
        logger.warning(f"Error during file cleanup: {e}")
        raise