#app.py

import os
import asyncio
import logging
import time
import math
import redis
from typing import Optional
from mutagen.mp3 import MP3
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import aiofiles
from pydantic import BaseModel
from dotenv import load_dotenv
from celery.result import AsyncResult
from tasks import process_audio_file, celery_app

# Import the API manager
from apimanager import APIKeyManager

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Configure templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Load environment variables
load_dotenv()

# Initialize API Key Manager
api_manager = APIKeyManager()

# Ensure uploads directory exists
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg'}

# Pydantic models for request/response validation
class AudioProcessRequest(BaseModel):
    media_path: str
    context: Optional[str] = ""

class AudioProcessResponse(BaseModel):
    task_id: str
    status: str
    message: str

class TaskStatusResponse(BaseModel):
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None

def calculate_estimated_processing_time(audio_length: float) -> int:
    """Calculate estimated processing time based on 3.5 seconds per minute of audio"""
    return math.ceil(audio_length / 60 * 6)

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_unique_filename(original_filename: str) -> str:
    """Generate a unique filename to prevent conflicts in concurrent uploads"""
    timestamp = int(time.time() * 1000)
    base_name, extension = os.path.splitext(original_filename)
    return f"{base_name}_{timestamp}{extension}"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    context: str = Form("")
):
    if not file:
        raise HTTPException(status_code=400, detail="No file part")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No selected file")

    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="File type not allowed")

    try:
        # Generate unique filename for concurrent uploads
        unique_filename = get_unique_filename(file.filename.replace(" ", "_"))
        media_path = os.path.join(UPLOAD_FOLDER, unique_filename)

        # Asynchronously save the file
        async with aiofiles.open(media_path, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)

        # Get audio file details and validate
        try:
            audio = MP3(media_path)
            audio_length = audio.info.length
            if audio_length <= 0:
                os.remove(media_path)
                raise ValueError("Invalid audio duration")
        except Exception as e:
            os.remove(media_path)
            raise HTTPException(
                status_code=400,
                detail=f"Invalid audio file: {str(e)}"
            )

        # Calculate estimated processing time
        estimated_processing_time = calculate_estimated_processing_time(audio_length)

        return {
            'audio_length_minutes': round(audio_length/60, 2),
            'audio_length_seconds': round(audio_length, 2),
            'estimated_time': estimated_processing_time,
            'media_path': media_path,
            'context': context,
            'message': 'File uploaded successfully'
        }

    except Exception as e:
        logger.error(f"Upload error: {e}")
        if os.path.exists(media_path):
            os.remove(media_path)
        raise HTTPException(status_code=500, detail=str(e))

async def verify_file_access(file_path: str) -> tuple[bool, Optional[str]]:
    """
    Verify that a file exists and is accessible.
    Returns (success, error_message)
    """
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        # Check if file is readable
        if not os.access(file_path, os.R_OK):
            return False, f"File is not readable: {file_path}"
        
        # Additional check for file size (optional)
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False, f"File is empty: {file_path}"
        
        return True, ""
    
    except Exception as e:
        return False, f"File access error: {str(e)}"

@app.post("/process_audio", response_model=AudioProcessResponse)
async def process_audio(
    file: UploadFile = File(...), 
    context: str = Form(""),
    request: Request = None
):
    """
    Process audio file asynchronously using Celery
    """
    try:
        logger.info("entered process_audio")
        # Check if a file is uploaded
        if not file or not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No audio file uploaded"
            )

        # Validate file type
        if not allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only MP3, WAV, and M4A files are allowed."
            )
        logger.info("file type validated")
        # Generate unique filename
        unique_filename = get_unique_filename(file.filename)
        media_path = os.path.join(UPLOAD_FOLDER, unique_filename)

        # Save the uploaded file
        with open(media_path, "wb") as buffer:
            buffer.write(await file.read())
        logger.info("saved file" )
        # Verify file access
        file_access_result, error_msg = await verify_file_access(media_path)
        if not file_access_result:
            os.remove(media_path)  # Clean up the file
            raise HTTPException(
                status_code=500,
                detail=f"File access error: {error_msg}"
            )

        # Get API key
        api_key = await api_manager.get_available_key()
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="No API key available. Please try again later."
            )
        logger.info("api_key: " + api_key)
        # Validate API key
        if api_key == 'YOUR_API_KEY' or not api_key:
            raise HTTPException(
                status_code=400,
                detail="Invalid API key. Please configure a valid Google Generative AI API key."
            )
        logger.info("validated api_key")
        logger.info(f"Submitting task with media_path={media_path}, api_key={api_key[:10]}..., context={context}")

        task = process_audio_file.delay(media_path, api_key, context)

        # Log task details
        logger.info(f"Task submitted: ID = {task.id}")

        # Connect to Redis
        redis_client = redis.StrictRedis(host='redis', port=6379, decode_responses=True)

        # Check the queue contents (default queue name is 'celery')
        queue_name = 'celery'
        queue_contents = redis_client.lrange(queue_name, 0, -1)

        # Log the queue contents
        logger.info(f"Current Redis Queue Contents ({queue_name}):")
        for idx, task_data in enumerate(queue_contents):
            logger.info(f"{idx + 1}: {task_data}")

        return AudioProcessResponse(
            task_id=task.id,
            status='Processing started',
            message='Audio processing task submitted successfully'
        )
    except Exception as e:
        logger.error(f"Error submitting task: {e}")
        if 'api_key' in locals() and api_key:
            await api_manager.release_key(api_key)
        raise

@app.get("/task_status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get the status of a Celery task with detailed information
    """
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        if task_result.ready():
            result = task_result.get()
            
            if task_result.successful():
                return TaskStatusResponse(
                    status='completed',
                    result={
                        'transcription': result.get('transcription', ''),
                        'success': result.get('success', False),
                        'task_id': result.get('task_id', task_id),
                        'processed_at': result.get('processed_at', ''),
                        'context': result.get('context', '')
                    }
                )
            else:
                return TaskStatusResponse(
                    status='failed',
                    error=result.get('error', 'Task failed without specific error')
                )
        
        # Handle in-progress tasks
        return TaskStatusResponse(
            status=task_result.state.lower(),
            result={'progress': 'Processing'} if task_result.state == 'STARTED' else None
        )
        
    except Exception as e:
        logger.error(f"Error checking task status: {e}")
        return TaskStatusResponse(
            status='error',
            error=f"Error checking task status: {str(e)}"
        )

@app.get("/results", response_class=HTMLResponse)
async def results(request: Request):
    return templates.TemplateResponse("results.html", {"request": request})

@app.get("/results/{task_id}", response_class=HTMLResponse)
async def get_results(request: Request, task_id: str):
    """
    Retrieve and render task results with extended waiting time
    """
    try:
        # Get the AsyncResult for the task
        task_result = AsyncResult(task_id, app=celery_app)
        
        # Wait for the task to complete with a longer timeout (e.g., 5 minutes)
        try:
            result = task_result.get(timeout=600)  # 5 minutes timeout
        except TimeoutError:
            logger.error(f"Task {task_id} timed out after 5 minutes")
            return templates.TemplateResponse("results.html", {
                "request": request, 
                "success": False, 
                "error": "Processing took too long. Please try again.",
                "task_id": task_id
            })
        except Exception as e:
            logger.error(f"Error retrieving task result for {task_id}: {e}", exc_info=True)
            return templates.TemplateResponse("results.html", {
                "request": request, 
                "success": False, 
                "error": f"Error processing audio: {str(e)}",
                "task_id": task_id
            })
        
        # Check if result is a dictionary with expected keys
        if not isinstance(result, dict):
            logger.error(f"Unexpected result type for task {task_id}: {type(result)}")
            return templates.TemplateResponse("results.html", {
                "request": request, 
                "success": False, 
                "error": "Unexpected result format",
                "task_id": task_id
            })
        
        # Process successful result
        if result.get('success', False):
            return templates.TemplateResponse("results.html", {
                "request": request,
                "success": True,
                "task_id": task_id,
                "transcription": result.get('transcription', 'No transcription available'),
                "context": result.get('context', ''),
                "processed_at": result.get('processed_at', '')
            })
        else:
            # Handle task failure
            error_message = result.get('error', 'Unknown error occurred during transcription')
            logger.error(f"Transcription failed for task {task_id}: {error_message}")
            
            return templates.TemplateResponse("results.html", {
                "request": request, 
                "success": False, 
                "error": error_message,
                "task_id": task_id
            })
        
    except Exception as e:
        logger.error(f"Unexpected error in get_results for {task_id}: {e}", exc_info=True)
        return templates.TemplateResponse("results.html", {
            "request": request, 
            "success": False, 
            "error": f"Unexpected error: {str(e)}",
            "task_id": task_id
        })

# Health check endpoint
@app.get("/health")
async def health_check():
    """
    Simple health check endpoint
    """
    return {"status": "healthy"}

# Error handling middleware
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """
    Custom HTTP exception handler
    """
    logger.error(f"HTTP Exception: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """
    Global exception handler for unexpected errors
    """
    logger.error(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "An unexpected error occurred"}
    )

# Optional: Include Celery app configuration if needed
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
