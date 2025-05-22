# Import bt_logging_patch before anything else
import bt_logging_patch

import sys
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from bitcast.validator.socials.youtube.youtube_evaluation import vet_video
from bitcast.validator.socials.youtube import youtube_utils
from bitcast.validator.utils.config import RAPID_API_KEY

# Configure logging to show all logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Note: This API is intended solely for the use of the subnet development team.
# It can be ignored by anyone else.

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

class VideoRequest(BaseModel):
    video_id: str
    briefs: List[Dict[str, Any]]
    video_data: Dict[str, Any]
    video_analytics: Dict[str, Any]

@app.post("/vet_video/")
async def vet_video_endpoint(request: VideoRequest):
    try:
        # Verify bt.logging mock is working
        logging.debug("=== Starting vet_video_endpoint ===")
        
        # Add debug logs
        logging.debug(f"Received request for video: {request.video_id}")
        logging.debug(f"Request contains {len(request.briefs)} briefs")
        
        # Call the vet_video function from youtube_scoring.py
        result = vet_video(
            video_id=request.video_id,
            briefs=request.briefs,
            video_data=request.video_data,
            video_analytics=request.video_analytics
        )
        
        # Log the result
        logging.debug(f"Result: met {len(result['met_brief_ids'])} briefs out of {len(request.briefs)}")

        # Return both the decision details and brief reasonings
        return result
    
    except Exception as e:
        logging.error(f"Error in vet_video_endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def main():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
