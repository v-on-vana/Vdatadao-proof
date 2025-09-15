import logging
import hashlib
from typing import Dict, Any, Optional

from my_proof.utils.db import DataRegistry, hash_email
from my_proof.config import settings

class EmailValidator:
    
    def __init__(self):
        
        try:
            self.data_registry = DataRegistry()
            self.db_available = True
        except Exception as e:
            logging.error(f"Data registry initialization failed: {str(e)}")
            self.db_available = False
    
    def validate_email_consistency(self, google_user: Optional[Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }
        
        if not google_user:
            validation_result["warnings"].append("NO_GOOGLE_USER")
            # Check contributor vs instagram email even if no Google user
        
        contributor_email = input_data.get('contributor', {}).get('email')
        instagram_profile_email = input_data.get('data', {}).get('profile', {}).get('email')
        
        # If Google user exists, check Google email
        if google_user:
            google_email = google_user.email
            
            if google_email != contributor_email:
                validation_result["is_valid"] = False
                validation_result["errors"].append("GOOGLE_CONTRIBUTOR_EMAIL_MISMATCH")
                logging.error(f"Google email {google_email} does not match contributor email {contributor_email}")
            
            if google_email != instagram_profile_email:
                validation_result["is_valid"] = False
                validation_result["errors"].append("GOOGLE_INSTAGRAM_EMAIL_MISMATCH")
                logging.error(f"Google email {google_email} does not match Instagram profile email {instagram_profile_email}")
        
        # BASIC CHECK: Contributor vs Instagram email (with or without Google user)
        if contributor_email != instagram_profile_email:
            validation_result["is_valid"] = False
            validation_result["errors"].append("CONTRIBUTOR_INSTAGRAM_EMAIL_MISMATCH")
            logging.error(f"Contributor email {contributor_email} does not match Instagram profile email {instagram_profile_email}")
        
        return validation_result
    
    def check_email_duplication(self, email: str) -> bool:
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping email duplication check")
                return False
            
            email_hash = hash_email(email)
            
            is_registered, registered_wallet = self.data_registry.is_email_hash_registered(email_hash)
            
            if is_registered:
                logging.warning(f"Email already registered: {email[:10]}... to wallet {registered_wallet[:10] if registered_wallet else 'unknown'}...")
                return True
            
            logging.info(f"Email validation passed for: {email[:10]}...")
            return False
            
        except Exception as e:
            logging.error(f"Error checking email duplication: {str(e)}")
            return False
    
    def register_email_to_database(self, email: str, wallet_address: str) -> bool:
        try:
            if not self.db_available:
                return False
            
            email_hash = hash_email(email)
            return self.data_registry.register_email_hash(email_hash, wallet_address)
                
        except Exception as e:
            logging.error(f"Error registering email: {str(e)}")
            return False
    
    def _hash_email(self, email: str) -> str:
        normalized_email = email.lower().strip()
        return hashlib.sha256(normalized_email.encode('utf-8')).hexdigest()
    
    
    
    def _extract_email_hash_from_metadata(self, file_metadata: Any) -> Optional[str]:
        try:
            if isinstance(file_metadata, dict):
                return file_metadata.get("email_hash")
            return None
        except Exception as e:
            logging.debug(f"Error extracting email hash from metadata: {str(e)}")
            return None
    
    def get_email_registration_info(self, email: str) -> Dict[str, Any]:
        try:
            email_hash = hash_email(email)
            
            if not self.db_available:
                return {"is_registered": False, "email_hash": email_hash}
            
            is_registered, registered_wallet = self.data_registry.is_email_hash_registered(email_hash)
            
            if not is_registered:
                return {
                    "is_registered": False,
                    "email_hash": email_hash
                }
            
            return {
                "is_registered": True,
                "email_hash": email_hash,
                "registered_wallet": registered_wallet,
                "registration_found": True
            }
            
        except Exception as e:
            logging.error(f"Error getting email registration info: {str(e)}")
            return {
                "is_registered": False,
                "email_hash": self._hash_email(email),
                "error": str(e)
            }
