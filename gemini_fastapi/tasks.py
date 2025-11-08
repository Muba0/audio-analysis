#tasks.py

from celery import Celery
import logging
import asyncio
import nest_asyncio
import google.generativeai as genai
from datetime import datetime
from gemini_fastapi.transcription import transcribe_audio, cleanup_file, validate_api_key
from celery.signals import task_success, task_failure
import os

# Apply nest_asyncio to handle event loops in multi-threaded environments
nest_asyncio.apply()

# Configure the Celery app
redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
celery_app = Celery('my_app', broker=redis_url, backend=redis_url)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def configure_genai(api_key: str):
    """
    Configure Google Generative AI with the provided API key
    """
    try:
        if not validate_api_key(api_key):
            raise ValueError("Invalid API key")
        genai.configure(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to configure Generative AI: {e}")
        raise

@celery_app.task(bind=True, 
                 soft_time_limit=300, 
                 time_limit=600, 
                 autoretry_for=(Exception,), 
                 retry_kwargs={'max_retries': 3, 'countdown': 5},
                 track_started=True)
def process_audio_file(self, media_path: str, api_key: str, context: str = None):
    """
    Celery task for processing audio files with consistent result structure
    """
    try:
        # Validate input arguments
        if not media_path or not api_key:
            raise ValueError("media_path and api_key must be provided")

        # Update task state to STARTED
        self.update_state(state='STARTED', meta={'status': 'Processing audio file'})

        # Configure Generative AI
        configure_genai(api_key)

        # Log received arguments
        logger.info(f"Received arguments - media_path: {media_path}, api_key: {api_key[:10]}..., context: {context}")

        # Run transcription synchronously
        logger.info(f"Starting transcription for: {media_path}")
        
        # Use asyncio.run to execute the async function
        result = asyncio.run(transcribe_audio(
            media_path=media_path,
            api_key=api_key,
            context=context,
            max_retries=3
        ))

        # Cleanup file after processing
        logger.info(f"Cleaning up file: {media_path}")
        asyncio.run(cleanup_file(media_path))

        # Ensure consistent result structure
        task_result = {
            'success': result.get('success', False),
            'task_id': self.request.id,
            'transcription': result.get('transcription', ''),
            'context': context or '',
            'processed_at': str(datetime.now()),
            'error': result.get('error', None)
        }

        # Update task state with the result
        self.update_state(
            state='SUCCESS',
            meta=task_result
        )



        return task_result

    except Exception as e:
        # Log the full exception details
        logger.error(f"Error processing audio file: {e}", exc_info=True)
        
        # Attempt to cleanup file even if processing fails
        try:
            asyncio.run(cleanup_file(media_path))
        except Exception as cleanup_error:
            logger.warning(f"File cleanup error: {cleanup_error}")
        
        # Prepare error result
        error_result = {
            'success': False,
            'task_id': self.request.id,
            'transcription': '',
            'context': context or '',
            'processed_at': str(datetime.now()),
            'error': str(e)
        }

        # Update task state with error
        self.update_state(
            state='FAILURE',
            meta=error_result
        )
        
        return error_result

# Task success signal handler
@task_success.connect
def handle_task_success(sender=None, result=None, **kwargs):
    logger.info(f"Task {sender} completed successfully with result]")

# Task failure signal handler
@task_failure.connect
def handle_task_failure(sender=None, exception=None, traceback=None, **kwargs):
    logger.error(f"Task {sender} failed with exception: {exception}")
    logger.error(f"Traceback: {traceback}")
