import logging
from typing import Dict, Any, List, Optional

from my_proof.processors.base_processor import BaseProcessor
from my_proof.models.proof_response import ProofResponse
from my_proof.scorers.google_scorer import GoogleScorer
from my_proof.validators.email_validator import EmailValidator

class GoogleProcessor(BaseProcessor):
    
    def __init__(self, proof_response: ProofResponse):
        self.proof_response = proof_response
        self.scorer = GoogleScorer()
        self.email_validator = EmailValidator()
    
    def process_data(self, input_data: Dict[str, Any], schema_matches: bool, google_user: Optional[Any], errors: List[str]) -> None:
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

        if google_user:
            profile_matches = self.verify_profile_match(google_user, input_data)
            if not profile_matches:
                errors.append("PROFILE_MISMATCH")
                logging.error(f"Input profile data does not match Google profile")

        quality_score = self.scorer.calculate_quality_score(input_data)
        authenticity_score = self.scorer.calculate_authenticity_score(input_data, google_user)
        uniqueness_score = self.scorer.calculate_uniqueness_score(input_data)
        ownership_score = self.scorer.calculate_ownership_score()

        self.proof_response.quality = quality_score
        self.proof_response.authenticity = authenticity_score
        self.proof_response.uniqueness = uniqueness_score
        self.proof_response.ownership = ownership_score

        self.proof_response.score = self.scorer.calculate_final_score(
            quality_score, authenticity_score, uniqueness_score, ownership_score
        )

        if contributor_email and wallet_address and len(errors) == 0:
            email_registered = self.email_validator.register_email_to_blockchain(contributor_email, wallet_address)
            if email_registered:
                logging.info(f"Email successfully registered to blockchain for wallet: {wallet_address[:10]}...")
            else:
                logging.warning(f"Failed to register email to blockchain for wallet: {wallet_address[:10]}...")

        self.proof_response.attributes = self.scorer.build_attributes(input_data, google_user)
        
        if contributor_email:
            email_info = self.email_validator.get_email_registration_info(contributor_email)
            self.proof_response.attributes.update({
                "email_validation": {
                    "email_consistency_check": email_validation_result["is_valid"],
                    "email_registered_to_blockchain": email_info.get("is_registered", False),
                    "email_hash": email_info.get("email_hash", "")[:16] + "..." if email_info.get("email_hash") else ""
                }
            })

    def verify_profile_match(self, google_user: Any, input_data: Dict[str, Any]) -> bool:
        if input_data.get("userId") != google_user.id:
            logging.error(
                f"User ID mismatch: {input_data.get('userId')} != {google_user.id}"
            )
            return False

        if input_data.get("email") != google_user.email:
            logging.error(
                f"Email mismatch: {input_data.get('email')} != {google_user.email}"
            )
            return False

        profile_name = input_data.get("profile", {}).get("name")
        if profile_name and profile_name != google_user.name:
            logging.error(f"Name mismatch: {profile_name} != {google_user.name}")
            return False

        logging.info("Google profile verification successful")
        return True
