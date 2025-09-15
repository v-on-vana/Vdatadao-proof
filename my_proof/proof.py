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
from my_proof.validators.email_validator import EmailValidator
from my_proof.config import settings

class Proof:
    # Main proof class - all validation operations are performed here
    
    def __init__(self):
        # Initial settings - preparing response object and validators
        self.proof_response = ProofResponse(dlp_id=settings.DLP_ID)
        self.duplicate_validator = DuplicateValidator()  # fake data checker
        self.email_validator = EmailValidator()  # email checker
        
    def generate(self) -> ProofResponse:
        # MAIN FUNCTION - All validation process runs here
        # Works with 6-stage control system
        logging.info("Starting proof generation for vdatadao with improved validation flow")
        errors = []

        # Google user verification (optional)
        google_user = self._get_google_user(errors)

        # Process JSON files in input folder one by one
        for input_filename in os.listdir(settings.INPUT_DIR):
            input_file = os.path.join(settings.INPUT_DIR, input_filename)

            if os.path.splitext(input_file)[1].lower() == ".json":
                # Load and parse file
                input_data = self._load_and_validate_file(input_file, errors)
                if not input_data:
                    continue
                
                # Extract basic information - we can't process without these
                contributor_email = input_data.get('contributor', {}).get('email')
                wallet_address = input_data.get('contributor', {}).get('wallet_address')
                
                if not contributor_email or not wallet_address:
                    errors.append("MISSING_CONTRIBUTOR_INFO")
                    logging.error("Missing contributor email or wallet address")
                    break
                
                # STAGE 1: SCHEMA VALIDATION - is data structure correct?
                logging.info("Step 1: Schema validation")
                schema_type, schema_matches = validate_schema(input_data)
                # Schema validation active - for real data testing
                if not schema_matches:
                    errors.append("INVALID_SCHEMA")
                    logging.error(f"Schema validation failed for {schema_type}")
                    break

                # STAGE 2: DUPLICATE DATA CHECK - most critical part!
                # Wallet, email, data hash, activity fingerprint all checked
                logging.info("Step 2: Duplicate data validation")
                is_duplicate, duplicate_reason = self.duplicate_validator.check_for_duplicate_data(
                    input_data, wallet_address, contributor_email
                )
                if is_duplicate:
                    errors.append(f"DUPLICATE_DATA: {duplicate_reason}")
                    logging.error(f"Duplicate data detected: {duplicate_reason}")
                    break

                # STAGE 3: EMAIL CONSISTENCY CHECK
                # Is contributor email same as Instagram email?
                logging.info("Step 3: Email consistency validation")
                email_validation_result = self.email_validator.validate_email_consistency(google_user, input_data)
                if not email_validation_result["is_valid"]:
                    errors.extend(email_validation_result["errors"])
                    logging.error(f"Email validation failed: {email_validation_result['errors']}")
                    break
                
                # Note: Email duplication is now checked within duplicate data validation
                
                # STAGE 4: RAW DATA CHECK
                # Is raw export data sufficient? Is size appropriate?
                logging.info("Step 4: Raw data validation")
                if not self._validate_raw_export_data_simple(input_data, errors):
                    logging.error("Raw data validation failed")
                    break

                # STAGE 5: DATA PROCESSING AND SCORING
                # Data is analyzed with Instagram/Google processor
                logging.info("Step 5: Processing data and calculating scores")
                self._process_data_by_type(input_data, schema_type, schema_matches, google_user, errors)
                
                # STAGE 6: SAVE TO DATABASE (only if no errors)
                # Permanently store valid data
                if len(errors) == 0:
                    logging.info("Step 6: Saving valid data to database")
                    data_saved = self.duplicate_validator.register_valid_data(input_data, wallet_address, contributor_email)
                    email_saved = self.email_validator.register_email_to_database(contributor_email, wallet_address)
                    
                    if not data_saved:
                        logging.warning("Failed to save data to database")
                    if not email_saved:
                        logging.warning("Failed to save email to database")

                self.proof_response.metadata = {
                    "schema_type": schema_type,
                    "validation_steps_completed": 6,
                    "duplicate_check_reason": duplicate_reason if is_duplicate else "NO_DUPLICATE"
                }

                self.proof_response.valid = len(errors) == 0
                logging.info(f"Proof generation completed with {len(errors)} errors")

        if len(errors) > 0:
            self.proof_response.attributes["errors"] = errors
            logging.error(f"Proof generation failed with errors: {errors}")

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


    def _validate_raw_export_data_simple(self, input_data, errors):
        # Checks if raw Instagram/Google export data is sufficient
        # To prevent submissions with fake minimal data
        try:
            data_section = input_data.get('data', {})
            profile = data_section.get('profile', {})
            
            # 1. Basic profile check - can't work without username and email
            if not profile.get('username') or not profile.get('email'):
                errors.append("MISSING_BASIC_PROFILE_DATA")
                return False
                
            # 2. Raw export data existence check - actual data is here
            raw_export_data = data_section.get('raw_export_data', {})
            if not raw_export_data:
                errors.append("MISSING_RAW_EXPORT_DATA")
                return False
                
            # 3. Category count check - suspicious if too few categories
            category_count = len(raw_export_data)
            if category_count < 3:
                errors.append("INSUFFICIENT_RAW_DATA_CATEGORIES")
                logging.warning(f"Raw data has only {category_count} categories, minimum 3 required")
                return False
                
            # 4. Content size calculation
            total_content_size = 0
            categories_with_content = 0
            
            for category_name, category_data in raw_export_data.items():
                if isinstance(category_data, dict) and 'content' in category_data:
                    content = category_data['content']
                    if content:  # Count if content is not empty
                        content_size = len(str(content))
                        total_content_size += content_size
                        categories_with_content += 1
                        
            # 5. Minimum size check - very small data might be fake
            min_required_size = 10000  # 10KB minimum
            if total_content_size < min_required_size:
                errors.append("INSUFFICIENT_RAW_DATA_SIZE")
                logging.warning(f"Raw data size {total_content_size} bytes, minimum {min_required_size} required")
                return False
                
            # 6. Content category check - at least 2 categories must be filled
            if categories_with_content < 2:
                errors.append("INSUFFICIENT_CONTENT_CATEGORIES")
                logging.warning(f"Only {categories_with_content} categories have content, minimum 2 required")
                return False
                
            logging.info(f"Raw export validation passed: {category_count} categories, {categories_with_content} with content, {total_content_size:,} bytes total")
            return True
            
        except Exception as e:
            logging.error(f"Error in raw export data validation: {str(e)}")
            errors.append("RAW_EXPORT_VALIDATION_ERROR")
            return False

    def _process_data_by_type(self, input_data, schema_type, schema_matches, google_user, errors):
        # Select correct processor based on data type - Instagram vs Google
        # Each platform has its own specific analysis method
        if schema_type == "instagram-meta-export.json":
            processor = InstagramProcessor(self.proof_response)  # Instagram data
            processor.process_data(input_data, schema_matches, google_user, errors)
        else:
            processor = GoogleProcessor(self.proof_response)  # Google data
            processor.process_data(input_data, schema_matches, google_user, errors)

