"""
FastAPI server for handling download requests from Chrome Extension
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Literal, Optional
import logging

# Configure logging

# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DownloadRequest(BaseModel):
    """Schema for download requests from extension"""
    url: str
    download_type: Literal["video", "audio"]
    is_playlist: bool = False
    quality: str = "1080p"
    format: str = "mp4"
    title: Optional[str] = "Untitled"


class DownloadResponse(BaseModel):
    """Response after queuing a download"""
    status: str
    message: str
    task_id: str


def create_app(download_manager):
    """Create and configure FastAPI application"""
    app = FastAPI(
        title="PyFlow Download Server",
        description="Local server for YouTube downloads via yt-dlp",
        version="1.0.0"
    )
    
    # CORS middleware to allow requests from Chrome Extension
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, specify extension origin
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint for extension to verify server is running"""
        return {
            "status": "online",
            "queue_size": download_manager.queue.qsize(),
            "active_downloads": len(download_manager.active_tasks)
        }
    
    @app.post("/add-download", response_model=DownloadResponse)
    async def add_download(request: DownloadRequest):
        """
        Add a new download task to the queue
        
        Args:
            request: DownloadRequest with URL, type, quality, format, etc.
            
        Returns:
            DownloadResponse with task ID and status
        """
        try:
            logger.info(f"Received download request: {request.title}")
            logger.info(f"URL: {request.url}")
            logger.info(f"Type: {request.download_type}, Quality: {request.quality}, Format: {request.format}")
            logger.info(f"Playlist: {request.is_playlist}")
            
            # Validate URL — accept any http/https URL (yt-dlp supports 1000+ sites)
            if not request.url.startswith(("http://", "https://")):
                raise HTTPException(
                    status_code=400,
                    detail="URL must start with http:// or https://"
                )
            
            # Add to download queue
            task_id = await download_manager.add_download(
                url=request.url,
                download_type=request.download_type,
                is_playlist=request.is_playlist,
                quality=request.quality,
                format_type=request.format,
                title=request.title
            )
            
            return DownloadResponse(
                status="success",
                message=f"Download queued successfully",
                task_id=task_id
            )
            
        except Exception as e:
            logger.error(f"Error adding download: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error queuing download: {str(e)}"
            )
    
    @app.get("/queue")
    async def get_queue_status():
        """Get current queue status and active downloads"""
        return {
            "queue_size": download_manager.queue.qsize(),
            "active_tasks": [
                {
                    "id": task.task_id,
                    "title": task.title,
                    "status": task.status,
                    "progress": task.progress
                }
                for task in download_manager.active_tasks.values()
            ]
        }
    
    @app.delete("/cancel/{task_id}")
    async def cancel_download(task_id: str):
        """Cancel a specific download task"""
        try:
            success = download_manager.cancel_task(task_id)
            if success:
                return {"status": "success", "message": f"Task {task_id} cancelled"}
            else:
                raise HTTPException(status_code=404, detail="Task not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    return app
