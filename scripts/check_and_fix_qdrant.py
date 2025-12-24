import sys
import os
import logging

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.glass_pane.qdrant_manager import qdrant_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qdrant_check")

def main():
    logger.info("Starting Qdrant Environment Check & Repair...")
    
    report = qdrant_manager.run_check_and_repair()
    
    if report["status"] == "error":
        logger.error(f"Critical Failure: {report['message']}")
        sys.exit(1)
    
    logger.info("Check Complete.")
    logger.info(f"Created Collections: {report['created']}")
    logger.info(f"Checked Collections: {report['checked']}")
    
    if report["status"] == "partial_failure":
        logger.warning("Some operations failed. Check logs.")
        sys.exit(1) # Fail build if schema isn't perfect
        
    logger.info("Qdrant Environment is Healthy.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
