import logging
from typing import Dict, Any, List, Optional

from my_proof.processors.base_processor import BaseProcessor
from my_proof.models.instagram import InstagramContribution
from my_proof.models.proof_response import ProofResponse
from my_proof.scorers.instagram_scorer import InstagramScorer
from my_proof.utils.ai_detector import AIDetector
from my_proof.validators.email_validator import EmailValidator
from my_proof.validators.duplicate_validator import DuplicateValidator

class InstagramProcessor(BaseProcessor):
    
    def __init__(self, proof_response: ProofResponse):
        self.proof_response = proof_response
        self.scorer = InstagramScorer()
        self.ai_detector = AIDetector()
        self.email_validator = EmailValidator()
        self.duplicate_validator = DuplicateValidator()
    
    def process_data(self, input_data: Dict[str, Any], schema_matches: bool, errors: List[str]) -> None:
        try:
            contributor_email = input_data.get('contributor', {}).get('email')
            wallet_address = input_data.get('contributor', {}).get('wallet_address')
            
            raw_export_size = 0
            if 'data' in input_data and 'raw_export_data' in input_data['data']:
                raw_export_data = input_data['data']['raw_export_data']
                if raw_export_data:
                    raw_export_size = len(str(raw_export_data))
                    logging.info(f"Processing contribution with raw_export_data (size: {raw_export_size} chars)")
                    
                    if raw_export_size > 1000000:
                        logging.warning(f"Large raw_export_data detected: {raw_export_size} chars")
            
            instagram_data = InstagramContribution(**input_data)

            quality_score = self.scorer.calculate_quality_score(instagram_data)
            authenticity_score = self.scorer.calculate_authenticity_score(instagram_data)
            uniqueness_score = self.scorer.calculate_uniqueness_score(instagram_data)
            ownership_score = self.scorer.calculate_ownership_score()

            self.proof_response.quality = quality_score
            self.proof_response.authenticity = authenticity_score
            self.proof_response.uniqueness = uniqueness_score
            self.proof_response.ownership = ownership_score

            self.proof_response.score = self.scorer.calculate_final_score(
                quality_score, authenticity_score, uniqueness_score, ownership_score
            )

            ai_result = None
            try:
                ai_result = self.ai_detector.detect_ai_content(instagram_data.dict())
            except Exception as e:
                logging.error(f"AI detection for attributes failed: {str(e)}")

            self.proof_response.attributes = self.scorer.build_attributes(
                instagram_data, ai_result
            )
            
            if contributor_email:
                email_info = self.email_validator.get_email_registration_info(contributor_email)
                self.proof_response.attributes.update({
                    "email_validation": {
                        "email_registered_to_database": email_info.get("is_registered", False),
                        "email_hash": email_info.get("email_hash", "")[:16] + "..." if email_info.get("email_hash") else ""
                    }
                })
            
            if contributor_email and wallet_address and len(errors) == 0:
                # Perform separate duplicate checks (Username, Email, Wallet, Timestamp)
                is_separate_duplicate, separate_reason = self.duplicate_validator.check_separate_duplicates(
                    input_data, wallet_address, contributor_email
                )
                
                if is_separate_duplicate:
                    errors.append(f"SEPARATE_DUPLICATE_DETECTED: {separate_reason}")
                    logging.error(f"Separate duplicate detected: {separate_reason}")
                else:
                    # Register all separate hashes if no duplicates found
                    logging.info(f"Registering separate hashes for: {contributor_email[:10]}...")
                    registration_success = self.duplicate_validator.register_separate_valid_data(
                        input_data, wallet_address, contributor_email
                    )
                    
                    if not registration_success:
                        errors.append("SEPARATE_REGISTRATION_FAILED")
                        logging.error("Failed to register separate hashes")
                    else:
                        logging.info("Successfully registered all separate hashes")
                
                # Add separate validation info to attributes
                self.proof_response.attributes.update({
                    "separate_validation": {
                        "separate_duplicate_check": not is_separate_duplicate,
                        "separate_duplicate_reason": separate_reason if is_separate_duplicate else "ALL_SEPARATE_CHECKS_PASSED"
                    }
                })

        except Exception as e:
            errors.append("INSTAGRAM_DATA_PROCESSING_ERROR")
            logging.error(f"Error processing Instagram data: {str(e)}")

            self.proof_response.quality = 0.0
            self.proof_response.authenticity = 0.0
            self.proof_response.uniqueness = 0.0
            self.proof_response.ownership = self.scorer.calculate_ownership_score()
            self.proof_response.score = 0.0

            self.proof_response.attributes = {
                "schema_type": "instagram-meta-export.json",
                "processing_error": str(e),
            }

    def verify_profile_match(self, google_user: Any, input_data: Dict[str, Any]) -> bool:
        return True
