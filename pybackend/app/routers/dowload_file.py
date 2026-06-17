from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
import os
import platform

router = APIRouter(
    prefix="/api/download_file",
    tags=["Download File"]
)

@router.get("/download")
def download_file(file_path: str = Query(...), file_id: int = Query(0)):
    # 1. First, try ONLY strict absolute path (Production Mode)
    # Per instructions: "In Python, always use the absolute file path exactly as sent by the UI."
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type="application/octet-stream"
        )
    
    # 2. If strict path fails, check if we are in a Local/Windows environment and try to map it.
    # This fixes the "File not found" error during local development on Windows
    # when the DB sends Linux production paths (e.g., /var/www/...)
    
    # Define local mapping logic
    # Production Path segment: .../UploadedFiles/...
    # Local Path equivalent:   .../API/UserPanel/UserPanel/UploadedFiles/...
    
    search_marker = "UploadedFiles"
    if search_marker in file_path:
        try:
            # Extract the part after (and including) UploadedFiles
            # e.g /var/www/.../UploadedFiles/Dir/File.pdf -> UploadedFiles/Dir/File.pdf
            relative_part = file_path.split(search_marker, 1)[1]
            relative_part = relative_part.lstrip('/\\') # clean leading slashes
            
            # Construct local path relative to this project
            # This logic assumes the python code is in [Project]/python/app/routers
            # And the files are in [Project]/API/UserPanel/UserPanel/UploadedFiles
            
            # Calculate Project Root from current file: .../python/app/routers/download_file.py
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Go up 3 levels to get to [Project] root (d:\DOWNLOADS\BTG-GASIGY-COMBINED)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
            
            local_fallback_path = os.path.join(
                project_root, 
                "API", "UserPanel", "UserPanel", "UploadedFiles", 
                relative_part
            )
            
            print(f"DEBUG: Strict path failed. Trying local fallback: '{local_fallback_path}'")
            
            if os.path.exists(local_fallback_path):
                return FileResponse(
                    path=local_fallback_path,
                    filename=os.path.basename(local_fallback_path),
                    media_type="application/octet-stream"
                )
        except Exception as e:
            print(f"DEBUG: Local fallback attempt failed: {e}")

    # 3. If both fail, return 404 and log debug info
    print(f"DEBUG: File not found at path: '{file_path}'")
    raise HTTPException(status_code=404, detail=f"File not found. Checked: {file_path}")