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
    
    def process_data(self, input_data: Dict[str, Any], schema_matches: bool, errors: List[str]) -> None:
        contributor_email = input_data.get('contributor', {}).get('email')
        wallet_address = input_data.get('contributor', {}).get('wallet_address')

        quality_score = self.scorer.calculate_quality_score(input_data)
        authenticity_score = self.scorer.calculate_authenticity_score(input_data)
        uniqueness_score = self.scorer.calculate_uniqueness_score(input_data)
        ownership_score = self.scorer.calculate_ownership_score()

        self.proof_response.quality = quality_score
        self.proof_response.authenticity = authenticity_score
        self.proof_response.uniqueness = uniqueness_score
        self.proof_response.ownership = ownership_score

        self.proof_response.score = self.scorer.calculate_final_score(
            quality_score, authenticity_score, uniqueness_score, ownership_score
        )

        self.proof_response.attributes = self.scorer.build_attributes(input_data)
        
        if contributor_email:
            email_info = self.email_validator.get_email_registration_info(contributor_email)
            self.proof_response.attributes.update({
                "email_validation": {
                    "email_registered_to_database": email_info.get("is_registered", False),
                    "email_hash": email_info.get("email_hash", "")[:16] + "..." if email_info.get("email_hash") else ""
                }
            })
        
        if contributor_email and wallet_address and len(errors) == 0:
            logging.info(f"Registering email to database: {contributor_email[:10]}...")
            self.email_validator.register_email_to_database(contributor_email, wallet_address)

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
