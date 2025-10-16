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
    logging.info(f"[DEBUG] Input directory: {settings.INPUT_DIR}")
    
    try:
        all_files = os.listdir(settings.INPUT_DIR)
        logging.info(f"[DEBUG] Found {len(all_files)} files to check")
    except Exception as e:
        logging.error(f"[DEBUG] Failed to list input directory: {e}")
        return
    
    for input_filename in all_files:
        input_file = os.path.join(settings.INPUT_DIR, input_filename)
        
        if os.path.isdir(input_file):
            logging.info(f"[DEBUG] Skipping directory: {input_filename}")
            continue
            
        file_size = os.path.getsize(input_file)
        logging.info(f"[DEBUG] Checking file: {input_filename} ({file_size:,} bytes)")

        is_zip = zipfile.is_zipfile(input_file)
        logging.info(f"[DEBUG] Is ZIP file: {is_zip}")
        
        if is_zip:
            logging.info(f"[DEBUG] Found ZIP file: {input_filename}")
            try:
                with zipfile.ZipFile(input_file, "r") as zip_ref:
                    file_list = zip_ref.namelist()
                    logging.info(f"[DEBUG] ZIP contains {len(file_list)} files")
                    logging.info(f"[DEBUG] Files in ZIP: {file_list[:10]}")
                    
                    zip_ref.extractall(settings.INPUT_DIR)
                    logging.info(f"[DEBUG] Extracted to: {settings.INPUT_DIR}")
                    
                    os.remove(input_file)
                    logging.info(f"[DEBUG] Removed original ZIP: {input_filename}")
                    
                    extracted_files = os.listdir(settings.INPUT_DIR)
                    logging.info(f"[DEBUG] After extraction: {extracted_files}")
            except zipfile.BadZipFile as e:
                logging.error(f"[DEBUG] BAD ZIP FILE: {input_filename}")
                logging.error(f"[DEBUG] Error: {str(e)}")
                logging.error(f"[DEBUG] File might be encrypted or corrupted")
                
                with open(input_file, 'rb') as f:
                    header = f.read(20)
                    logging.error(f"[DEBUG] File header (hex): {header.hex()}")
                    logging.error(f"[DEBUG] File header (bytes): {header}")
            except Exception as e:
                logging.error(f"[DEBUG] Failed to extract {input_filename}: {str(e)}")
                import traceback
                logging.error(f"[DEBUG] Traceback: {traceback.format_exc()}")
        else:
            logging.info(f"[DEBUG] NOT a ZIP file: {input_filename}")
            
            if input_filename.endswith('.zip'):
                logging.warning(f"[DEBUG] File has .zip extension but is not a valid ZIP")
                with open(input_file, 'rb') as f:
                    header = f.read(20)
                    logging.warning(f"[DEBUG] File header: {header.hex()}")
    
    logging.info(f"[DEBUG] ZIP extraction process completed")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        logging.error(f"Error during proof generation: {e}")
        traceback.print_exc()
        sys.exit(1)
