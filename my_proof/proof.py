# vdatadao proof generation system - modular architecture for instagram & google data validation

import logging
import os
from datetime import datetime, timezone

from my_proof.models.proof_response import ProofResponse
from my_proof.utils.google import get_google_user
from my_proof.utils.schema import validate_schema
from my_proof.processors.instagram_processor import InstagramProcessor
from my_proof.processors.google_processor import GoogleProcessor
from my_proof.validators.duplicate_validator import DuplicateValidator
from my_proof.config import settings

class Proof:
    def __init__(self):
        self.proof_response = ProofResponse(dlp_id=settings.DLP_ID)
        self.duplicate_validator = DuplicateValidator()
        
    def generate(self) -> ProofResponse:
        logging.info("Starting proof generation for vdatadao ")
        errors = []

        google_user = self._get_google_user(errors)

        for input_filename in os.listdir(settings.INPUT_DIR):
            logging.info(f"Checking file: {input_filename}")
            input_file = os.path.join(settings.INPUT_DIR, input_filename)

            if os.path.splitext(input_file)[1].lower() == ".json":
                input_data = self._load_and_validate_file(input_file, errors)
                if not input_data:
                    continue
                    
                schema_type, schema_matches = validate_schema(input_data)
                if not schema_matches:
                    errors.append(f"INVALID_SCHEMA")
                    break

                if self._check_duplicates(input_data, errors):
                    break

                if self._validate_raw_export_data(input_data, errors):
                    self._process_data_by_type(input_data, schema_type, schema_matches, google_user, errors)
                else:
                    break

                self.proof_response.metadata = {
                    "schema_type": schema_type,
                }

                self.proof_response.valid = len(errors) == 0

        if len(errors) > 0:
            self.proof_response.attributes["errors"] = errors

        return self.proof_response

    def _get_google_user(self, errors):
        google_user = None
        if settings.GOOGLE_TOKEN:
            google_user = get_google_user()
            if google_user:
                if not google_user.verified_email:
                    errors.append("UNVERIFIED_STORAGE_EMAIL")
            else:
                errors.append("UNVERIFIED_STORAGE_USER")
        else:
            logging.info("GOOGLE_TOKEN not set, skipping user verification")
        return google_user

    def _load_and_validate_file(self, input_file, errors):
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                json_content = f.read()
                logging.info(f"Validating file: {json_content[:50]}...")
                import json
                return json.loads(json_content)
        except Exception as e:
            logging.error(f"Error loading file {input_file}: {str(e)}")
            errors.append("FILE_LOADING_ERROR")
            return None

    def _check_duplicates(self, input_data, errors):
        contributor = input_data.get('contributor', {})
        wallet_address = contributor.get('wallet_address')
        contributor_email = contributor.get('email')
        
        if self.duplicate_validator.blockchain_available and wallet_address and contributor_email:
            if self.duplicate_validator.check_for_duplicate_data(input_data, wallet_address, contributor_email):
                errors.append("DUPLICATE_DATA_DETECTED")
                logging.warning(f"Duplicate data detected for wallet: {wallet_address[:10]}...")
                return True
        return False

    def _validate_raw_export_data(self, input_data, errors):
        try:
            is_valid, validation_errors, completeness_score = self.duplicate_validator.validate_raw_export_data(input_data)
            
            if not is_valid:
                errors.extend(validation_errors)
                logging.error(f"Raw export data validation failed: {validation_errors}")
                return False
            
            logging.info(f"Raw export data validation passed: {completeness_score:.1f}% complete")
            return True
            
        except Exception as e:
            logging.error(f"Error in raw export data validation: {str(e)}")
            errors.append("RAW_EXPORT_VALIDATION_ERROR")
            return False

    def _process_data_by_type(self, input_data, schema_type, schema_matches, google_user, errors):
        if schema_type == "instagram-meta-export.json":
            processor = InstagramProcessor(self.proof_response)
            processor.process_data(input_data, schema_matches, google_user, errors)
        else:
            processor = GoogleProcessor(self.proof_response)
            processor.process_data(input_data, schema_matches, google_user, errors)

