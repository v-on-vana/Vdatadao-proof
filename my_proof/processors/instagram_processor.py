import logging
from typing import Dict, Any, List, Optional

from my_proof.processors.base_processor import BaseProcessor
from my_proof.models.instagram import InstagramContribution
from my_proof.models.proof_response import ProofResponse
from my_proof.scorers.instagram_scorer import InstagramScorer
from my_proof.utils.ai_detector import AIDetector
from my_proof.validators.email_validator import EmailValidator

class InstagramProcessor(BaseProcessor):
    
    def __init__(self, proof_response: ProofResponse):
        self.proof_response = proof_response
        self.scorer = InstagramScorer()
        self.ai_detector = AIDetector()
        self.email_validator = EmailValidator()
    
    def process_data(self, input_data: Dict[str, Any], schema_matches: bool, google_user: Optional[Any], errors: List[str]) -> None:
        try:
            email_validation_result = self.email_validator.validate_email_consistency(google_user, input_data)
            
            if not email_validation_result["is_valid"]:
                errors.extend(email_validation_result["errors"])
                logging.error(f"Email validation failed: {email_validation_result['errors']}")
            
            if email_validation_result["warnings"]:
                logging.warning(f"Email validation warnings: {email_validation_result['warnings']}")
            
            contributor_email = input_data.get('contributor', {}).get('email')
            wallet_address = input_data.get('contributor', {}).get('wallet_address')
            
            if contributor_email and self.email_validator.check_email_duplication(contributor_email):
                errors.append("EMAIL_ALREADY_REGISTERED")
                logging.error(f"Email {contributor_email[:10]}... is already registered in blockchain")
            
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
            authenticity_score = self.scorer.calculate_authenticity_score(instagram_data, google_user)
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

            if contributor_email and wallet_address and len(errors) == 0:
                email_registered = self.email_validator.register_email_to_blockchain(contributor_email, wallet_address)
                if email_registered:
                    logging.info(f"Email successfully registered to blockchain for wallet: {wallet_address[:10]}...")
                else:
                    logging.warning(f"Failed to register email to blockchain for wallet: {wallet_address[:10]}...")

            self.proof_response.attributes = self.scorer.build_attributes(
                instagram_data, google_user, ai_result
            )
            
            if contributor_email:
                email_info = self.email_validator.get_email_registration_info(contributor_email)
                self.proof_response.attributes.update({
                    "email_validation": {
                        "email_consistency_check": email_validation_result["is_valid"],
                        "email_registered_to_blockchain": email_info.get("is_registered", False),
                        "email_hash": email_info.get("email_hash", "")[:16] + "..." if email_info.get("email_hash") else ""
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
                "verified_with_oauth": google_user is not None,
            }

    def verify_profile_match(self, google_user: Any, input_data: Dict[str, Any]) -> bool:
        return True
