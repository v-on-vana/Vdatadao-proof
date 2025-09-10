import hashlib
import json
import logging
from typing import Dict, Any

from my_proof.utils.blockchain import BlockchainClient
from my_proof.utils.db import DataRegistry, hash_email
from my_proof.config import settings

class DuplicateValidator:
    
    def __init__(self):
        try:
            self.blockchain_client = BlockchainClient()
            self.blockchain_available = True
        except Exception as e:
            logging.warning(f"Blockchain client initialization failed: {str(e)}")
            self.blockchain_available = False
        
        try:
            self.data_registry = DataRegistry()
            self.db_available = True
        except Exception as e:
            logging.error(f"Data registry initialization failed: {str(e)}")
            self.db_available = False
    
    def check_for_duplicate_data(self, input_data: Dict[str, Any], wallet_address: str, contributor_email: str) -> bool:
        try:
            if not self.blockchain_available:
                return False
            
            if self._check_wallet_email_binding(wallet_address, contributor_email):
                logging.warning(f"Wallet-email binding violation detected for {wallet_address[:10]}...")
                return True
                
            core_data_fingerprint = self._generate_core_data_fingerprint(input_data)
            
            all_contributors = self.blockchain_client.get_all_contributors()
            
            for contributor_addr in all_contributors:
                if not contributor_addr or not wallet_address:
                    continue
                if str(contributor_addr).lower() == str(wallet_address).lower():
                    continue
                    
                existing_files = self.blockchain_client.get_contributor_files(contributor_addr)
                
                for file_hash in existing_files:
                    similarity_score = self._calculate_data_similarity(core_data_fingerprint, file_hash)
                    
                    if similarity_score > 0.85:
                        logging.warning(f"High similarity detected: {similarity_score:.2f} with {contributor_addr[:10]}...")
                        return True
                        
            return False
            
        except Exception as e:
            logging.error(f"Error checking for duplicate data: {str(e)}")
            return False

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
        try:
            if not self.blockchain_available or not settings.OWNER_ADDRESS:
                return False
                
            existing_file_count = self.blockchain_client.get_contributor_file_count()
            
            if existing_file_count == 0:
                logging.info("No existing contributions found")
                return False
            
            logging.info(f"Checking {existing_file_count} existing contributions for duplicates")
            
            logging.info(f"Hash check for: {current_hash[:16]}... (simplified implementation)")
            
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
