import json
import logging
import os
import sys
import traceback
import zipfile

from my_proof.proof import Proof
from my_proof.config import settings

logging.basicConfig(level=logging.INFO, format="%(message)s")


def run() -> None:
    """Generate proofs for all input files."""
    if not settings.DLP_ID or settings.DLP_ID == 0:
        settings.DLP_ID = 42

    input_files_exist = os.path.isdir(settings.INPUT_DIR) and bool(
        os.listdir(settings.INPUT_DIR)
    )

    if not input_files_exist:
        raise FileNotFoundError(f"No input files found in {settings.INPUT_DIR}")
    
    logging.info(f"Input directory: {settings.INPUT_DIR}")
    logging.info(f"Files found: {os.listdir(settings.INPUT_DIR)}")
    
    extract_input()

    proof = Proof()
    proof_response = proof.generate()

    output_path = os.path.join(settings.OUTPUT_DIR, "results.json")
    with open(output_path, "w") as f:
        json.dump(proof_response.model_dump(), f, indent=2)
    logging.info(f"Proof generation complete: {proof_response}")


def extract_input() -> None:
    """If the input directory contains any zip files, extract them"""
    logging.info("[DEBUG] Starting ZIP extraction process")
    
    for input_filename in os.listdir(settings.INPUT_DIR):
        input_file = os.path.join(settings.INPUT_DIR, input_filename)
        logging.info(f"[DEBUG] Checking file: {input_filename}")

        if zipfile.is_zipfile(input_file):
            logging.info(f"[DEBUG] ✅ Found ZIP file: {input_filename}")
            try:
                with zipfile.ZipFile(input_file, "r") as zip_ref:
                    file_list = zip_ref.namelist()
                    logging.info(f"[DEBUG] ZIP contains {len(file_list)} files")
                    logging.info(f"[DEBUG] First 10 files: {file_list[:10]}")
                    
                    zip_ref.extractall(settings.INPUT_DIR)
                    logging.info(f"[DEBUG] ✅ Extracted to: {settings.INPUT_DIR}")
                    
                    extracted_files = os.listdir(settings.INPUT_DIR)
                    logging.info(f"[DEBUG] After extraction, directory contains: {extracted_files}")
            except Exception as e:
                logging.error(f"[DEBUG] ❌ Failed to extract {input_filename}: {str(e)}")
        else:
            logging.info(f"[DEBUG] Not a ZIP file: {input_filename}")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logging.error(f"Error during proof generation: {e}")
        traceback.print_exc()
        sys.exit(1)
