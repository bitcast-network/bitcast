# Import bt_logging_patch before anything else
import bt_logging_patch

import sys
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from bitcast.validator.platforms.youtube.evaluation.video.orchestration import vet_video
import asyncio
import json

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
        # Log the incoming request
        logging.info(f"Incoming /vet_video/ request: {request.json()}")
        
        # Verify bt.logging mock is working
        logging.debug("=== Starting vet_video_endpoint ===")
        
        # Spoof video data for testing - always override publish date to bypass date validation
        spoofed_video_data = request.video_data.copy()
        # Always set a recent date (within the last 30 days) to ensure it passes date validation
        from datetime import datetime, timedelta
        recent_date = (datetime.now() - timedelta(days=15)).isoformat() + "Z"
        spoofed_video_data["publishedAt"] = recent_date
        
        # Spoof brief dates for testing - override start_date and end_date to bypass date validation
        spoofed_briefs = []
        for brief in request.briefs:
            spoofed_brief = brief.copy()
            
            # Set brief dates to current timeframe to ensure date validation passes
            # Brief should start before video publish date and end after it
            brief_start = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
            brief_end = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
            
            spoofed_brief["start_date"] = brief_start
            spoofed_brief["end_date"] = brief_end
            
            spoofed_briefs.append(spoofed_brief)
        
        # Offload synchronous vet_video call to a thread to avoid blocking
        result = await asyncio.to_thread(
            vet_video,
            video_id=request.video_id,
            briefs=spoofed_briefs,
            video_data=spoofed_video_data,
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
    import multiprocessing
    multiprocessing.set_start_method('fork', force=True)
    import uvicorn, os
    uvicorn.run("internal_api:app", host="0.0.0.0", port=7999, workers=os.cpu_count())

if __name__ == "__main__":
    main()
