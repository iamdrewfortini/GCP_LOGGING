import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import json
import logging
from src.services.redis_service import redis_service
from src.workers.main import worker_loop

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_pipeline")

async def test_pipeline():
    queue_name = "q:embeddings:realtime"
    
    # 1. Enqueue a test task
    test_task = {
        "session_id": "test-session-123",
        "project_id": "test-project",
        "role": "user",
        "content": "This is a test message to verify the pipeline."
    }
    
    logger.info("Step 1: Enqueueing task...")
    success = redis_service.enqueue(queue_name, test_task)
    if success:
        logger.info("Task enqueued successfully.")
    else:
        logger.error("Failed to enqueue task.")
        return

    # 2. Verify it's in Redis (optional peek)
    # In a real test, we might check list length, but let's just run the worker.

    # 3. Run worker for a short burst
    logger.info("Step 2: Running worker to consume task...")
    try:
        # We'll run the worker loop for a few seconds then cancel it
        worker = asyncio.create_task(worker_loop())
        await asyncio.sleep(3) 
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            logger.info("Worker stopped.")
            
    except Exception as e:
        logger.error(f"Worker failed: {e}")

if __name__ == "__main__":
    # Load .env variables if needed (dotenv usually handles this in apps)
    # But here we rely on the environment being set or .env file being present
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(test_pipeline())
