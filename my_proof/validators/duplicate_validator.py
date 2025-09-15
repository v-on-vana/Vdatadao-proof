import hashlib
import json
import logging
from typing import Dict, Any, Tuple

from my_proof.utils.db import DataRegistry, hash_email
from my_proof.config import settings

class DuplicateValidator:
    # This class performs fake/duplicate data detection - the most important security component
    
    def __init__(self):
        # Establish database connection, otherwise it won't work
        try:
            self.data_registry = DataRegistry()
            self.db_available = True
        except Exception as e:
            logging.error(f"Data registry initialization failed: {str(e)}")
            self.db_available = False
        
        # Hash cache - for performance, we don't recalculate the same hashes
        self._cached_hashes = None
    
    def check_for_duplicate_data(self, input_data: Dict[str, Any], wallet_address: str, contributor_email: str) -> Tuple[bool, str]:                                                                             
        # NEW SYSTEM: Check each field separately - more reliable duplicate detection
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping duplicate data check")
                return False, "DATABASE_UNAVAILABLE"
            
            # Extract immutable fields
            immutable_data = self.extract_immutable_fields(input_data)
            
            if not immutable_data:
                logging.warning("No immutable data found for duplicate check")
                return False, "NO_IMMUTABLE_DATA"
            
            # 1. FIRST: INDIVIDUAL FIELD CHECKS
            is_duplicate, reason = self.check_individual_duplicates(immutable_data, wallet_address)
            
            if is_duplicate:
                logging.warning(f"Individual field duplicate detected for {wallet_address[:10]}...: {reason}")
                return True, reason
            
            # 2. THEN: GENERAL DATA HASH CHECK
            data_hash = self.calculate_data_hash(input_data)
            fingerprint = self._generate_core_data_fingerprint(input_data)
            email_hash = hash_email(contributor_email)
            
            if not data_hash or not fingerprint:
                logging.error("Failed to generate data hash or fingerprint")
                return False, "HASH_GENERATION_ERROR"
            
            # Cache hashes - to reuse in register_valid_data
            self._cached_hashes = {
                'data_hash': data_hash,
                'fingerprint': fingerprint,
                'email_hash': email_hash
            }
            
            # General data hash check
            is_duplicate, reason = self.data_registry.check_data_duplicate(
                data_hash, fingerprint, wallet_address, email_hash
            )
            
            if is_duplicate:
                logging.warning(f"Data hash duplicate detected for {wallet_address[:10]}...: {reason}")
                return True, reason
            
            logging.info(f"No duplicate found for {wallet_address[:10]}...: {reason}")
            return False, reason
            
        except Exception as e:
            logging.error(f"Error checking for duplicate data: {str(e)}")
            return False, f"ERROR: {str(e)}"

    def extract_immutable_fields(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts immutable fields from Instagram data.
        
        WHY ADDED: Provides more reliable control by using only immutable fields 
        (timestamp, email, phone, username) for duplicate detection.
        """
        immutable_data = {}
        
        # Extract reliable data from raw export data
        raw_export_data = input_data.get('data', {}).get('raw_export_data', {})
        if raw_export_data:
            # Parse content of each category
            for category_name, category_data in raw_export_data.items():
                if isinstance(category_data, dict) and 'content' in category_data:
                    content = category_data['content']
                    try:
                        import json
                        content_json = json.loads(content)

                        # Account creation timestamp (signup_details.json) - NEVER CHANGES
                        if 'account_creation_timestamp' in content_json:
                            timestamp = content_json['account_creation_timestamp']
                            # Ensure millisecond precision
                            if isinstance(timestamp, (int, float)):
                                # Convert to milliseconds if in seconds
                                if timestamp < 10000000000:  # If less than 10 billion, it's in seconds
                                    timestamp = int(timestamp * 1000)
                                immutable_data['account_creation_timestamp'] = timestamp

                        # Email (personal_information.json) - PERSONAL
                        if 'email' in content_json:
                            immutable_data['email'] = content_json['email']

                        # Phone number (personal_information.json) - PERSONAL
                        if 'phone_number' in content_json:
                            immutable_data['phone_number'] = content_json['phone_number']

                        # Username (personal_information.json) - PERSONAL
                        if 'username' in content_json:
                            immutable_data['username'] = content_json['username']
                            
                    except:
                        pass
        
        # Clean empty values
        immutable_data = {k: v for k, v in immutable_data.items() if v != '' and v is not None}
        return immutable_data

    def check_individual_duplicates(self, immutable_data: Dict[str, Any], wallet_address: str) -> Tuple[bool, str]:                                                                                              
        """
        Checks each immutable field separately for duplicates.
        
        WHY ADDED: Provides more sensitive duplicate detection by checking 
        each field separately instead of using a single hash.
        
        Returns:
            Tuple[bool, str]: (is_duplicate, reason)
        """
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping individual duplicate checks")
                return False, "NO_DUPLICATE"
            
            # 1. Account creation timestamp check - MOST IMPORTANT
            if 'account_creation_timestamp' in immutable_data:
                timestamp = immutable_data['account_creation_timestamp']
                # Check through data registry
                is_duplicate, reason = self.data_registry.check_timestamp_duplicate(timestamp, wallet_address)
                if is_duplicate:
                    logging.warning(f"Same Instagram account (timestamp: {timestamp}) already used: {reason}")
                    return True, reason
            
            # 2. Email check - existing system
            if 'email' in immutable_data:
                email = immutable_data['email']
                email_hash = hashlib.sha256(email.lower().encode('utf-8')).hexdigest()
                
                # Existing email registry check
                is_registered, registered_wallet = self.data_registry.is_email_hash_registered(email_hash)
                if is_registered and registered_wallet != wallet_address:
                    logging.warning(f"Email {email} already used by wallet {registered_wallet}")
                    return True, f"EMAIL_ALREADY_USED_BY_WALLET_{registered_wallet}"
            
            # 3. Phone check - new system
            if 'phone_number' in immutable_data:
                phone = immutable_data['phone_number']
                phone_hash = hashlib.sha256(phone.encode('utf-8')).hexdigest()
                
                is_duplicate, reason = self.data_registry.check_phone_duplicate(phone_hash, wallet_address)
                if is_duplicate:
                    logging.warning(f"Phone {phone} already used: {reason}")
                    return True, reason
            
            # 4. Username check - new system
            if 'username' in immutable_data:
                username = immutable_data['username']
                username_hash = hashlib.sha256(username.lower().encode('utf-8')).hexdigest()
                
                is_duplicate, reason = self.data_registry.check_username_duplicate(username_hash, wallet_address)
                if is_duplicate:
                    logging.warning(f"Username {username} already used: {reason}")
                    return True, reason
            
            return False, "NO_DUPLICATE"
            
        except Exception as e:
            logging.error(f"Error in individual duplicate check: {str(e)}")
            return False, "ERROR_IN_DUPLICATE_CHECK"

    def calculate_data_hash(self, input_data: Dict[str, Any]) -> str:
        """Calculate data hash for the complete immutable data set"""
        try:
            immutable_data = self.extract_immutable_fields(input_data)
            
            if not immutable_data:
                logging.warning("No immutable data found in input")
                return ""

            data_size = len(str(immutable_data))
            logging.info(f"Extracting immutable data for hash (size: {data_size} chars)")
            logging.info(f"Immutable data: {list(immutable_data.keys())}")

            # Normalize JSON and get SHA256 hash
            normalized_json = json.dumps(immutable_data, sort_keys=True, separators=(',', ':'))
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
        # MOST IMPORTANT FUNCTION! Fake data detection is performed here
        # We look at following, post, like activities - not profile information
        try:
            data_section = input_data.get('data', {})
            activities = data_section.get('activities', {})
            
            # Activity-based fingerprint - profile independent
            activity_fingerprint = {}
            
            # Following list signature - prevents fake following lists
            following_list = activities.get('following_list', [])
            if following_list and len(following_list) >= 3:
                # Get signature of ALL followed users - for strong detection
                following_signature = []
                for follow in following_list:  # include all following data
                    if follow.get('username') and follow.get('followed_at'):
                        following_signature.append({
                            'username': follow.get('username'),  # who they followed
                            'followed_at': follow.get('followed_at')  # when they followed
                        })
                activity_fingerprint['following_signature'] = following_signature
            
            # Post signature - prevents fake post data
            posts_created = activities.get('posts_created', [])
            if posts_created:
                posts_signature = []
                for post in posts_created:  # get all posts
                    if post.get('creation_timestamp'):
                        posts_signature.append({
                            'creation_timestamp': post.get('creation_timestamp'),  # post time
                            'title': post.get('title', ''),  # post title
                            'source_app': post.get('source_app'),  # which app
                            'has_photo': post.get('has_photo'),  # has photo
                            'has_camera_metadata': post.get('has_camera_metadata')  # camera info
                        })
                activity_fingerprint['posts_signature'] = posts_signature
            
            # Like signature - prevents fake like data
            likes_given = activities.get('likes_given', [])
            if likes_given:
                likes_signature = []
                for like in likes_given:
                    likes_signature.append({
                        'target_username': like.get('target_username'),  # who they liked
                        'count': like.get('count'),  # how many times
                        'last_activity': like.get('last_activity')  # last activity
                    })
                activity_fingerprint['likes_signature'] = likes_signature
            
            # Comment signature - fake comment detection
            comments_made = activities.get('comments_made', [])
            if comments_made:
                comments_signature = []
                for comment in comments_made:
                    if comment.get('timestamp'):
                        comments_signature.append({
                            'timestamp': comment.get('timestamp'),  # comment time
                            'content': comment.get('content', '')[:20]  # first 20 characters
                        })
                activity_fingerprint['comments_signature'] = comments_signature
            
            # If no important activity, use basic profile
            if not activity_fingerprint:
                profile = data_section.get('profile', {})
                activity_fingerprint = {
                    'username': profile.get('username'),
                    'account_type': profile.get('account_type')
                }
            
            # Convert activity fingerprint to hash
            fingerprint_json = json.dumps(activity_fingerprint, sort_keys=True, separators=(',', ':'))
            fingerprint_hash = hashlib.sha256(fingerprint_json.encode('utf-8')).hexdigest()
            
            logging.info(f"Generated activity fingerprint: {fingerprint_hash[:16]}... from {len(activity_fingerprint)} activity types")
            return fingerprint_hash
            
        except Exception as e:
            logging.error(f"Error generating activity fingerprint: {str(e)}")
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
        # Register successfully validated data to database
        # We store wallet + data hash + fingerprint so we can check later
        try:
            if not self.db_available:
                logging.warning("Database not available, skipping data registration")
                return False
            
            # Get hashes from cache - instead of recalculating (PERFORMANCE OPTIMIZATION!)
            if hasattr(self, '_cached_hashes') and self._cached_hashes:
                data_hash = self._cached_hashes['data_hash']
                fingerprint = self._cached_hashes['fingerprint']
                email_hash = self._cached_hashes['email_hash']
                logging.info("Using cached hashes for registration (performance optimization)")
            else:
                # If no cache, recalculate (fallback)
                logging.warning("No cached hashes found, recalculating...")
                data_hash = self.calculate_data_hash(input_data)
                fingerprint = self._generate_core_data_fingerprint(input_data)
                email_hash = hash_email(contributor_email)
            
            if not data_hash or not fingerprint:
                logging.error("Failed to generate data hash or fingerprint for registration")
                return False
            
            contribution_id = input_data.get('contribution_id')
            platform = input_data.get('data', {}).get('platform', 'instagram')
            
            # First register wallet (since this is the first submission for this wallet)
            wallet_success = self.data_registry.register_wallet(
                wallet_address, email_hash, data_hash, platform
            )
            
            # Then register data hash
            data_success = self.data_registry.register_data_hash(
                data_hash, fingerprint, wallet_address, email_hash, contribution_id, platform
            )
            
            # Also add Phone and Username registrations
            immutable_data = self.extract_immutable_fields(input_data)
            
            # Phone registration
            if 'phone_number' in immutable_data:
                phone = immutable_data['phone_number']
                phone_hash = hashlib.sha256(phone.encode('utf-8')).hexdigest()
                self.data_registry.register_phone_hash(phone_hash, wallet_address)
                logging.info(f"Phone hash registered for wallet {wallet_address[:10]}...")
            
            # Username registration
            if 'username' in immutable_data:
                username = immutable_data['username']
                username_hash = hashlib.sha256(username.lower().encode('utf-8')).hexdigest()
                self.data_registry.register_username_hash(username_hash, wallet_address)
                logging.info(f"Username hash registered for wallet {wallet_address[:10]}...")
            
            # Timestamp registration
            if 'account_creation_timestamp' in immutable_data:
                timestamp = immutable_data['account_creation_timestamp']
                self.data_registry.register_timestamp(timestamp, wallet_address)
                logging.info(f"Timestamp {timestamp} registered for wallet {wallet_address[:10]}...")
            
            # Clear cache - for next submission
            if hasattr(self, '_cached_hashes'):
                delattr(self, '_cached_hashes')
            
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
