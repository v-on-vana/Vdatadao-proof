import json
import logging
import os
import sys
import traceback
import zipfile
from pathlib import Path

from my_proof.proof import Proof
from my_proof.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def run() -> None:
    """Generate proofs for all input files."""
    logger.info("Starting proof generation...")
    logger.info(f"Input directory: {settings.INPUT_DIR}")
    logger.info(f"Output directory: {settings.OUTPUT_DIR}")
    logger.info(f"Database path: {settings.DATABASE_PATH}")
    
    # Check if input directory exists and has files
    input_path = Path(settings.INPUT_DIR)
    if not input_path.exists():
        logger.error(f"Input directory does not exist: {settings.INPUT_DIR}")
        raise FileNotFoundError(f"Input directory does not exist: {settings.INPUT_DIR}")
    
    input_files = list(input_path.glob("*"))
    if not input_files:
        logger.error(f"No input files found in {settings.INPUT_DIR}")
        raise FileNotFoundError(f"No input files found in {settings.INPUT_DIR}")
    
    logger.info(f"Found {len(input_files)} input files")
    
    # Extract zip files if any
    extract_input()
    
    # Create output directory if it doesn't exist
    output_path = Path(settings.OUTPUT_DIR)
    output_path.mkdir(parents=True, exist_ok=True)
    
    try:
        proof = Proof()
        proof_response = proof.generate()
        
        # Write results
        result_file = output_path / "results.json"
        with open(result_file, "w") as f:
            json.dump(proof_response.model_dump(), f, indent=2)
        
        logger.info(f"Proof generation complete: {proof_response}")
        logger.info(f"Results saved to: {result_file}")
        
    except Exception as e:
        logger.error(f"Error during proof generation: {e}")
        traceback.print_exc()
        
        # Write error results
        error_response = {
            "dlp_id": settings.DLP_ID,
            "valid": False,
            "score": 0.0,
            "authenticity": 0.0,
            "ownership": 0.0,
            "quality": 0.0,
            "uniqueness": 0.0,
            "attributes": {
                "error": str(e),
                "error_type": type(e).__name__
            },
            "metadata": {
                "error_occurred": True,
                "input_dir": settings.INPUT_DIR,
                "output_dir": settings.OUTPUT_DIR
            }
        }
        
        result_file = output_path / "results.json"
        with open(result_file, "w") as f:
            json.dump(error_response, f, indent=2)
        
        raise


def extract_input() -> None:
    """If the input directory contains any zip files, extract them"""
    input_path = Path(settings.INPUT_DIR)
    
    for input_file in input_path.glob("*.zip"):
        logger.info(f"Extracting zip file: {input_file}")
        try:
            with zipfile.ZipFile(input_file, "r") as zip_ref:
                zip_ref.extractall(input_path)
            logger.info(f"Successfully extracted: {input_file}")
        except Exception as e:
            logger.error(f"Error extracting {input_file}: {e}")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)
