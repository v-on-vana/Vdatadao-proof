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
    def __init__(self):
        self.proof_response = ProofResponse(dlp_id=settings.DLP_ID)
        self.duplicate_validator = DuplicateValidator()
        self.email_validator = EmailValidator()
        
    def generate(self) -> ProofResponse:
        logging.info("Starting proof generation for vdatadao ")
        errors = []

        google_user = self._get_google_user(errors)

        for input_filename in os.listdir(settings.INPUT_DIR):
            input_file = os.path.join(settings.INPUT_DIR, input_filename)

            if os.path.splitext(input_file)[1].lower() == ".json":
                input_data = self._load_and_validate_file(input_file, errors)
                if not input_data:
                    continue
                    
                schema_type, schema_matches = validate_schema(input_data)
                if not schema_matches:
                    errors.append(f"INVALID_SCHEMA")
                    break

                # EMAIL CONSISTENCY CHECK - EN ÖNCELİKLİ
                email_validation_result = self.email_validator.validate_email_consistency(google_user, input_data)
                if not email_validation_result["is_valid"]:
                    errors.extend(email_validation_result["errors"])
                    logging.error(f"Email validation failed: {email_validation_result['errors']}")
                    break
                
                # DATABASE DUPLICATE CHECK
                contributor_email = input_data.get('contributor', {}).get('email')
                if contributor_email and self.email_validator.check_email_duplication(contributor_email):
                    errors.append("EMAIL_ALREADY_REGISTERED")
                    logging.error(f"Email {contributor_email[:10]}... already registered")
                    break
                
                # SCORE CALCULATION & DATABASE REGISTRATION
                self._process_data_by_type(input_data, schema_type, schema_matches, google_user, errors)
                
                # Raw data validation - simplified check
                if not self._validate_raw_export_data_simple(input_data, errors):
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


    def _validate_raw_export_data_simple(self, input_data, errors):
        try:
            data_section = input_data.get('data', {})
            profile = data_section.get('profile', {})
            
            # 1. Profile temel kontrolü
            if not profile.get('username') or not profile.get('email'):
                errors.append("MISSING_BASIC_PROFILE_DATA")
                return False
                
            # 2. Raw export data varlığı kontrolü
            raw_export_data = data_section.get('raw_export_data', {})
            if not raw_export_data:
                errors.append("MISSING_RAW_EXPORT_DATA")
                return False
                
            # 3. Kategori sayısı kontrolü (minimum 3 kategori olmalı)
            category_count = len(raw_export_data)
            if category_count < 3:
                errors.append("INSUFFICIENT_RAW_DATA_CATEGORIES")
                logging.warning(f"Raw data has only {category_count} categories, minimum 3 required")
                return False
                
            # 4. İçerik boyutu kontrolü
            total_content_size = 0
            categories_with_content = 0
            
            for category_name, category_data in raw_export_data.items():
                if isinstance(category_data, dict) and 'content' in category_data:
                    content = category_data['content']
                    if content:  # Content boş değilse
                        content_size = len(str(content))
                        total_content_size += content_size
                        categories_with_content += 1
                        
            # 5. Minimum data size kontrolü (en az 10KB raw data olmalı)
            min_required_size = 10000  # 10KB
            if total_content_size < min_required_size:
                errors.append("INSUFFICIENT_RAW_DATA_SIZE")
                logging.warning(f"Raw data size {total_content_size} bytes, minimum {min_required_size} required")
                return False
                
            # 6. İçerikli kategori kontrolü (en az 2 kategori içerik sahibi olmalı)
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
        if schema_type == "instagram-meta-export.json":
            processor = InstagramProcessor(self.proof_response)
            processor.process_data(input_data, schema_matches, google_user, errors)
        else:
            processor = GoogleProcessor(self.proof_response)
            processor.process_data(input_data, schema_matches, google_user, errors)

