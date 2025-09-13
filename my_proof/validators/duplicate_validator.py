import hashlib
import json
import logging
from typing import Dict, Any, Tuple

from my_proof.utils.db import DataRegistry, hash_email
from my_proof.config import settings

class DuplicateValidator:
    
    def __init__(self):
        
        try:
            self.data_registry = DataRegistry()
            self.db_available = True
        except Exception as e:
            logging.error(f"Data registry initialization failed: {str(e)}")
            self.db_available = False
    
    def check_for_duplicate_data(self, input_data: Dict[str, Any], wallet_address: str, contributor_email: str) -> Tuple[bool, str]:
        """
        Complete duplicate data validation with wallet+email+data combination rules.
        
        Returns:
            Tuple: (is_duplicate: bool, reason: str)
        """
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping duplicate data check")
                return False, "DATABASE_UNAVAILABLE"
            
            data_hash = self.calculate_data_hash(input_data)
            fingerprint = self._generate_core_data_fingerprint(input_data)
            email_hash = hash_email(contributor_email)
            
            if not data_hash or not fingerprint:
                logging.error("Failed to generate data hash or fingerprint")
                return False, "HASH_GENERATION_ERROR"
            
            is_duplicate, reason = self.data_registry.check_data_duplicate(
                data_hash, fingerprint, wallet_address, email_hash
            )
            
            if is_duplicate:
                logging.warning(f"Duplicate data detected for {wallet_address[:10]}...: {reason}")
                return True, reason
            
            logging.info(f"No duplicate found for {wallet_address[:10]}...: {reason}")
            return False, reason
            
        except Exception as e:
            logging.error(f"Error checking for duplicate data: {str(e)}")
            return False, f"ERROR: {str(e)}"

    def calculate_data_hash(self, input_data: Dict[str, Any]) -> str:
        try:
            normalized_data = json.loads(json.dumps(input_data))
            
            fields_to_exclude = [
                'created_at', 'updated_at', 'processing_timestamp',
                'collection_date', 'metadata.processing_timestamp',
                'metadata.collection_date', 'data.raw_export_data'
            ]
            
            for field_path in fields_to_exclude:
                self._remove_nested_field(normalized_data, field_path)
            
            data_size = len(str(normalized_data))
            logging.info(f"Normalizing data for hash (size: {data_size} chars)")
            
            normalized_json = json.dumps(normalized_data, sort_keys=True, separators=(',', ':'))
            data_hash = hashlib.sha256(normalized_json.encode('utf-8')).hexdigest()
            
            logging.info(f"Calculated data hash: {data_hash[:16]}...")
            return data_hash
            
        except (MemoryError, UnicodeError) as e:
            logging.error(f"Memory/encoding error in hash calculation: {str(e)}")
            return self._calculate_simple_hash(input_data)
        except Exception as e:
            logging.error(f"Error calculating data hash: {str(e)}")
            return self._calculate_simple_hash(input_data)

    def is_duplicate_data(self, current_hash: str) -> bool:
        """
        Check if a data hash already exists in the database.
        
        Args:
            current_hash: SHA256 hash of the data to check
            
        Returns:
            bool: True if hash exists, False otherwise
        """
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping hash check")
                return False
            
            is_registered, registered_wallet, registered_email = self.data_registry.is_data_hash_registered(current_hash)
            
            if is_registered:
                logging.info(f"Hash {current_hash[:16]}... found in database: wallet {registered_wallet[:10] if registered_wallet else 'unknown'}...")
                return True
            
            logging.info(f"Hash {current_hash[:16]}... not found in database")
            return False
            
        except Exception as e:
            logging.error(f"Error checking for duplicate data: {str(e)}")
            return False

    def _generate_core_data_fingerprint(self, input_data: Dict[str, Any]) -> str:
        try:
            profile = input_data.get('data', {}).get('profile', {})
            
            core_fingerprint = {
                'username': profile.get('username'),
                'email': hashlib.sha256(str(profile.get('email', '')).encode('utf-8')).hexdigest(),
                'account_type': profile.get('account_type')
            }
            
            fingerprint_json = json.dumps(core_fingerprint, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(fingerprint_json.encode('utf-8')).hexdigest()
            
        except Exception as e:
            logging.error(f"Error generating core data fingerprint: {str(e)}")
            return ""

    def _calculate_data_similarity(self, current_fingerprint: str, existing_hash: str) -> float:
        try:
            if current_fingerprint == existing_hash:
                return 1.0
                
            current_bytes = bytes.fromhex(current_fingerprint) if len(current_fingerprint) == 64 else current_fingerprint.encode()
            existing_bytes = bytes.fromhex(existing_hash) if len(existing_hash) == 64 else existing_hash.encode()
            
            matching_bits = sum(a == b for a, b in zip(current_bytes, existing_bytes))
            total_bits = max(len(current_bytes), len(existing_bytes))
            
            similarity = matching_bits / total_bits if total_bits > 0 else 0.0
            
            if similarity > 0.7:
                logging.info(f"Data similarity detected: {similarity:.2f}")
                
            return similarity
            
        except Exception as e:
            logging.error(f"Error calculating data similarity: {str(e)}")
            return 0.0

    def _remove_nested_field(self, data: Dict[str, Any], field_path: str) -> None:
        try:
            keys = field_path.split('.')
            current_level = data
            
            for key in keys[:-1]:
                if isinstance(current_level, dict) and key in current_level:
                    current_level = current_level[key]
                else:
                    return
            
            if isinstance(current_level, dict) and keys[-1] in current_level:
                del current_level[keys[-1]]
                logging.debug(f"Removed field: {field_path}")
                
        except (KeyError, TypeError, AttributeError):
            pass

    def _calculate_simple_hash(self, input_data: Dict[str, Any]) -> str:
        try:
            profile = input_data.get('data', {}).get('profile', {})
            
            core_data = {
                'contribution_id': input_data.get('contribution_id'),
                'contributor': input_data.get('contributor', {}),
                'data': {
                    'platform': input_data.get('data', {}).get('platform'),
                    'profile': {
                        'username': profile.get('username'),
                        'email': hashlib.sha256(str(profile.get('email', '')).encode('utf-8')).hexdigest(),
                        'account_type': profile.get('account_type')
                    }
                }
            }
            
            core_json = json.dumps(core_data, sort_keys=True, separators=(',', ':'))
            simple_hash = hashlib.sha256(core_json.encode('utf-8')).hexdigest()
            
            logging.info(f"Using simple hash calculation: {simple_hash[:16]}...")
            return simple_hash
            
        except Exception as e:
            logging.error(f"Simple hash calculation failed: {str(e)}")
            fallback_data = input_data.get('contribution_id', str(input_data))
            return hashlib.sha256(str(fallback_data).encode('utf-8')).hexdigest()

    def _check_wallet_email_binding(self, wallet_address: str, contributor_email: str) -> bool:
        try:
            if not contributor_email or not self.db_available:
                return False
                
            email_hash = hash_email(contributor_email)
            is_registered, registered_wallet = self.data_registry.is_email_hash_registered(email_hash)
            
            if is_registered and registered_wallet and str(registered_wallet).lower() != str(wallet_address).lower():
                logging.warning(f"Email {contributor_email[:10]}... already registered to different wallet {str(registered_wallet)[:10]}...")
                return True
            
            if not is_registered:
                self.data_registry.register_email_hash(email_hash, wallet_address)
                
            return False
            
        except Exception as e:
            logging.error(f"Error checking wallet-email binding: {str(e)}")
            return False

    def register_valid_data(self, input_data: Dict[str, Any], wallet_address: str, contributor_email: str) -> bool:
        """
        Register valid data hash, fingerprint and wallet to the database.
        
        Args:
            input_data: The validated input data
            wallet_address: Wallet address of the contributor
            contributor_email: Email of the contributor
            
        Returns:
            bool: True if registration successful
        """
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping data registration")
                return False
            
            data_hash = self.calculate_data_hash(input_data)
            fingerprint = self._generate_core_data_fingerprint(input_data)
            email_hash = hash_email(contributor_email)
            
            if not data_hash or not fingerprint:
                logging.error("Failed to generate data hash or fingerprint for registration")
                return False
            
            contribution_id = input_data.get('contribution_id')
            platform = input_data.get('data', {}).get('platform', 'instagram')
            
            # Register wallet first (since this is the first time for this wallet)
            wallet_success = self.data_registry.register_wallet(
                wallet_address, email_hash, data_hash, platform
            )
            
            # Register data hash
            data_success = self.data_registry.register_data_hash(
                data_hash, fingerprint, wallet_address, email_hash, contribution_id, platform
            )
            
            if wallet_success and data_success:
                logging.info(f"Successfully registered wallet and data for {wallet_address[:10]}...")
                return True
            else:
                logging.error(f"Failed to register wallet or data for {wallet_address[:10]}... (wallet: {wallet_success}, data: {data_success})")
                return False
            
        except Exception as e:
            logging.error(f"Error registering valid data: {str(e)}")
            return False

    def validate_raw_export_data(self, input_data: Dict[str, Any]) -> tuple:
        try:
            data_section = input_data.get('data', {})
            
            if not data_section.get('raw_export_data'):
                return False, ["MISSING_RAW_EXPORT_DATA"], 0.0
            
            required_sections = ['profile', 'activities', 'metrics']
            required_fields = ['username', 'email', 'account_type', 'posts_count', 'following_count', 'follower_count']
            
            found_fields = 0
            total_required = len(required_fields)
            
            profile = data_section.get('profile', {})
            activities = data_section.get('activities', {})
            metrics = data_section.get('metrics', {})
            
            if profile.get('username'): found_fields += 1
            if profile.get('email'): found_fields += 1  
            if profile.get('account_type'): found_fields += 1
            if metrics.get('posts_count') is not None: found_fields += 1
            if metrics.get('following_count') is not None: found_fields += 1
            if metrics.get('follower_count') is not None: found_fields += 1
            
            completeness_score = (found_fields / total_required) * 100.0
            is_valid = completeness_score >= 70.0
            
            return is_valid, [], completeness_score
            
        except Exception as e:
            logging.error(f"Error validating raw export data: {str(e)}")
            return False, ["RAW_EXPORT_VALIDATION_ERROR"], 0.0
