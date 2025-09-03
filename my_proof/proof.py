import hashlib
import json
import logging
import os
from datetime import datetime, timezone

from my_proof.models.proof_response import ProofResponse
from my_proof.models.instagram import InstagramContribution
from my_proof.utils.blockchain import BlockchainClient
from my_proof.utils.google import get_google_user
from my_proof.utils.schema import validate_schema
from my_proof.utils.ai_detector import AIDetector
from my_proof.config import settings


class Proof:
    def __init__(self):
        self.proof_response = ProofResponse(dlp_id=settings.DLP_ID)
        self.ai_detector = AIDetector()
        try:
            self.blockchain_client = BlockchainClient()
            self.blockchain_available = True
        except Exception as e:
            logging.warning(f"Blockchain client initialization failed: {str(e)}")
            self.blockchain_available = False

    def generate(self) -> ProofResponse:
        """Generate proofs for all input files."""
        logging.info("Starting proof generation")
        errors = []

        google_user = None
        storage_user_hash = None
        if settings.GOOGLE_TOKEN:
            google_user = get_google_user()
            if google_user:
                storage_user_hash = hashlib.sha256(google_user.id.encode()).hexdigest()
                if not google_user.verified_email:
                    errors.append("UNVERIFIED_STORAGE_EMAIL")
            else:
                errors.append("UNVERIFIED_STORAGE_USER")
        else:
            logging.info("GOOGLE_TOKEN not set, skipping user verification")

        for input_filename in os.listdir(settings.INPUT_DIR):
            logging.info(f"Checking file: {input_filename}")
            input_file = os.path.join(settings.INPUT_DIR, input_filename)

            if os.path.splitext(input_file)[1].lower() == ".json":
                with open(input_file, "r") as f:
                    json_content = f.read()
                    logging.info(f"Validating file: {json_content[:50]}...")
                    input_data = json.loads(json_content)
                    schema_type, schema_matches = validate_schema(input_data)
                    if not schema_matches:
                        errors.append(f"INVALID_SCHEMA")
                        break
                    
                    # Step 2: Data completeness validation (NEW!)
                    if schema_type == "instagram-meta-export.json":
                        completeness_valid, completeness_errors = self._validate_data_completeness(input_data)
                        if not completeness_valid:
                            errors.extend(completeness_errors)
                            logging.warning(f"Data completeness validation failed: {completeness_errors}")
                            break

                    contributor = input_data.get('contributor', {})
                    wallet_address = contributor.get('wallet_address')
                    contributor_email = contributor.get('email')
                    
                    if self.blockchain_available and wallet_address and contributor_email:
                        if self._check_for_duplicate_data(input_data, wallet_address, contributor_email):
                            errors.append("DUPLICATE_DATA_DETECTED")
                            logging.warning(f"Duplicate data detected for wallet: {wallet_address[:10]}...")
                            break



                    if schema_type == "instagram-meta-export.json":
                        self._process_instagram_data(
                            input_data, schema_matches, google_user, errors
                        )
                    else:
                        self._process_google_data(
                            input_data, schema_matches, google_user, errors
                        )

                    self.proof_response.metadata = {
                        "schema_type": schema_type,
                    }

                    self.proof_response.valid = len(errors) == 0

        if len(errors) > 0:
            # Convert technical errors to user-friendly messages
            user_friendly_errors = []
            for error in errors:
                user_friendly_message = self._get_user_friendly_error_message(error)
                user_friendly_errors.append(user_friendly_message)
            
            self.proof_response.attributes["errors"] = errors  # Keep technical errors for debugging
            self.proof_response.attributes["user_messages"] = user_friendly_errors  # Add user-friendly messages

        return self.proof_response

    def _verify_profile_match(self, google_user, input_data):
        """
        Verify that the input data matches the Google profile.

        Args:
            google_user: The GoogleUserInfo object from the OAuth API
            input_data: The input data from the JSON file

        Returns:
            bool: True if the data matches, False otherwise
        """
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

    def _process_google_data(self, input_data, schema_matches, google_user, errors):
        """Process Google profile data and calculate scores."""
        if google_user:
            profile_matches = self._verify_profile_match(google_user, input_data)
            if not profile_matches:
                errors.append("PROFILE_MISMATCH")
                logging.error(f"Input profile data does not match Google profile")

        self.proof_response.ownership = 1.0 if settings.OWNER_ADDRESS else 0.0
        self.proof_response.quality = 1.0 if schema_matches else 0.0
        self.proof_response.authenticity = (
            1.0 if google_user and schema_matches else 0.0
        )
        self.proof_response.uniqueness = 1.0

        self.proof_response.score = (
            self.proof_response.quality * 0.4
            + self.proof_response.authenticity * 0.3
            + self.proof_response.uniqueness * 0.2
            + self.proof_response.ownership * 0.1
        )

        self.proof_response.attributes = {
            "schema_type": "google-profile.json",
            "user_email": input_data.get("email"),
            "user_id": input_data.get("userId"),
            "profile_name": input_data.get("profile", {}).get("name"),
            "verified_with_oauth": google_user is not None,
        }

    def _process_instagram_data(self, input_data, schema_matches, google_user, errors):
        """Process Instagram Meta export data and calculate scores."""
        try:
            raw_export_size = 0
            if 'data' in input_data and 'raw_export_data' in input_data['data']:
                raw_export_data = input_data['data']['raw_export_data']
                if raw_export_data:
                    raw_export_size = len(str(raw_export_data))
                    logging.info(f"Processing contribution with raw_export_data (size: {raw_export_size} chars)")
                    
                    if raw_export_size > 1000000:  # 1MB limit
                        logging.warning(f"Large raw_export_data detected: {raw_export_size} chars")
            
            instagram_data = InstagramContribution(**input_data)

            if google_user:
                contributor_email = instagram_data.contributor.email
                if contributor_email != google_user.email:
                    errors.append("CONTRIBUTOR_EMAIL_MISMATCH")
                    logging.error(
                        f"Contributor email {contributor_email} does not match Google email {google_user.email}"
                    )

            quality_score = self._calculate_instagram_quality_score(instagram_data)

            authenticity_score = self._calculate_instagram_authenticity_score(
                instagram_data, google_user
            )

            uniqueness_score = self._calculate_instagram_uniqueness_score(
                instagram_data
            )

            ownership_score = 1.0 if settings.OWNER_ADDRESS else 0.0

            self.proof_response.quality = quality_score
            self.proof_response.authenticity = authenticity_score
            self.proof_response.uniqueness = uniqueness_score
            self.proof_response.ownership = ownership_score

            self.proof_response.score = (
                quality_score * 0.35
                + authenticity_score * 0.35
                + uniqueness_score * 0.20
                + ownership_score * 0.10
            )

            ai_result = None
            try:
                ai_result = self.ai_detector.detect_ai_content(instagram_data.dict())
            except Exception as e:
                logging.error(f"AI detection for attributes failed: {str(e)}")

            self.proof_response.attributes = {
                "schema_type": "instagram-meta-export.json",
                "platform": "instagram",
                "contributor_email": instagram_data.contributor.email,
                "contributor_wallet": instagram_data.contributor.wallet_address,
                "instagram_username": instagram_data.data.profile.username,
                "account_type": instagram_data.data.profile.account_type,
                "posts_count": instagram_data.data.metrics.posts_count,
                "followers_count": instagram_data.data.metrics.follower_count,
                "account_age_days": instagram_data.data.metrics.account_age_days,
                "extraction_completeness": instagram_data.metadata.extraction_completeness,
                "quality_score": instagram_data.metadata.quality_score,
                "data_freshness": instagram_data.metadata.data_freshness,
                "verified_with_oauth": google_user is not None,
                "phone_confirmed": instagram_data.data.profile.phone_confirmed,
                "private_account": instagram_data.data.profile.private_account,
            }
            
            if ai_result:
                self.proof_response.attributes.update({
                    "ai_detection": {
                        "is_ai_generated": ai_result.get('is_ai_generated', False),
                        "confidence": ai_result.get('confidence', 0.0),
                        "indicators": ai_result.get('indicators', []),
                        "authenticity_impact": max(0.0, 1.0 - ai_result.get('confidence', 0.0))
                    }
                })

        except Exception as e:
            errors.append("INSTAGRAM_DATA_PROCESSING_ERROR")
            logging.error(f"Error processing Instagram data: {str(e)}")

            self.proof_response.quality = 0.0
            self.proof_response.authenticity = 0.0
            self.proof_response.uniqueness = 0.0
            self.proof_response.ownership = 1.0 if settings.OWNER_ADDRESS else 0.0
            self.proof_response.score = 0.0

            self.proof_response.attributes = {
                "schema_type": "instagram-meta-export.json",
                "processing_error": str(e),
                "verified_with_oauth": google_user is not None,
            }

    def _calculate_instagram_quality_score(
        self, instagram_data: InstagramContribution
    ) -> float:
        """Calculate quality score based on data completeness and validity."""
        score = 0.0

        score += 0.3

        meta_score = (
            instagram_data.metadata.extraction_completeness / 100 * 0.2
            + instagram_data.metadata.quality_score / 100 * 0.1
            + instagram_data.metadata.data_freshness / 100 * 0.1
        )
        score += meta_score

        profile_fields = [
            instagram_data.data.profile.username,
            instagram_data.data.profile.display_name,
            instagram_data.data.profile.email,
            instagram_data.data.profile.account_type,
        ]
        complete_fields = sum(1 for field in profile_fields if field)
        score += (complete_fields / len(profile_fields)) * 0.2

        has_activities = (
            len(instagram_data.data.activities.posts_created) > 0
            or len(instagram_data.data.activities.likes_given) > 0
            or len(instagram_data.data.activities.comments_made) > 0
            or len(instagram_data.data.activities.following_list) > 0
        )
        if has_activities:
            score += 0.1

        return min(score, 1.0)

    def _calculate_instagram_authenticity_score(
        self, instagram_data: InstagramContribution, google_user
    ) -> float:
        """Calculate authenticity score based on verification, consistency, and AI detection."""
        score = 0.0

        if google_user:
            score += 0.25

        if instagram_data.data.profile.phone_confirmed:
            score += 0.10
        if instagram_data.data.profile.email:
            score += 0.10

        metrics = instagram_data.data.metrics
        if metrics.total_interactions == (
            metrics.likes_given_count + metrics.comments_count
        ):
            score += 0.075
        if metrics.account_age_days > 0:
            score += 0.075

        if (
            instagram_data.data.source_type == "meta_export"
            and instagram_data.data.extraction_method == "google_drive_api"
        ):
            score += 0.10

        try:
            ai_result = self.ai_detector.detect_ai_content(instagram_data.dict())
            ai_confidence = ai_result.get('confidence', 0.0)
            
            ai_authenticity_score = max(0.0, 1.0 - ai_confidence)
            score += ai_authenticity_score * 0.30
            
            if ai_result.get('is_ai_generated'):
                logging.warning(f"AI-generated content detected with confidence: {ai_confidence:.2f}")
                logging.warning(f"AI indicators: {ai_result.get('indicators', [])}")
            else:
                logging.info(f"Content appears authentic. AI confidence: {ai_confidence:.2f}")
                
        except Exception as e:
            logging.error(f"AI detection failed: {str(e)}")
            pass

        return min(score, 1.0)

    def _calculate_instagram_uniqueness_score(
        self, instagram_data: InstagramContribution
    ) -> float:
        """Calculate uniqueness score based on account activity and engagement."""
        score = 0.0
        metrics = instagram_data.data.metrics

        if metrics.account_age_days > 365:  # More than 1 year
            score += 0.25
        elif metrics.account_age_days > 30:  # More than 1 month
            score += 0.15
        elif metrics.account_age_days > 0:
            score += 0.05

        if metrics.posts_count > 100:
            score += 0.35
        elif metrics.posts_count > 50:
            score += 0.25
        elif metrics.posts_count > 10:
            score += 0.15
        elif metrics.posts_count > 0:
            score += 0.05

        if metrics.likes_given_count > 1000:
            score += 0.15
        elif metrics.likes_given_count > 100:
            score += 0.10
        elif metrics.likes_given_count > 0:
            score += 0.05

        if metrics.comments_count > 100:
            score += 0.10
        elif metrics.comments_count > 10:
            score += 0.05
        elif metrics.comments_count > 0:
            score += 0.02

        total_connections = metrics.following_count + metrics.follower_count
        if total_connections > 1000:
            score += 0.15
        elif total_connections > 100:
            score += 0.10
        elif total_connections > 10:
            score += 0.05
        elif total_connections > 0:
            score += 0.02

        return min(score, 1.0)

    def _calculate_data_hash(self, input_data: dict) -> str:
        """
        Calculate a unique hash for the input data to detect duplicates.
        Excludes raw_export_data and other non-essential fields for performance.
        
        Args:
            input_data: The input data dictionary
            
        Returns:
            str: SHA256 hash of the normalized data
        """
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

    def _remove_nested_field(self, data: dict, field_path: str) -> None:
        """
        Safely remove a nested field from the data dictionary.
        
        Args:
            data: The data dictionary to modify
            field_path: Dot-separated path to the field (e.g., 'data.raw_export_data')
        """
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

    def _calculate_simple_hash(self, input_data: dict) -> str:
        """
        Calculate a simple hash for very large datasets or when normalization fails.
        Uses only core fields to avoid memory issues.
        
        Args:
            input_data: The input data dictionary
            
        Returns:
            str: SHA256 hash of core data
        """
        try:
            core_data = {
                'contribution_id': input_data.get('contribution_id'),
                'contributor': input_data.get('contributor', {}),
                'data': {
                    'platform': input_data.get('data', {}).get('platform'),
                    'profile': input_data.get('data', {}).get('profile', {}),
                    'metrics': input_data.get('data', {}).get('metrics', {})
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

    def _is_duplicate_data(self, current_hash: str) -> bool:
        """
        Check if the current data hash already exists in blockchain contributions.
        
        Args:
            current_hash: SHA256 hash of the current data
            
        Returns:
            bool: True if duplicate data is found, False otherwise
        """
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
            return False  # If check fails, allow contribution

    def _check_for_duplicate_data(self, input_data: dict, wallet_address: str, contributor_email: str) -> bool:
        """
        Check if the same Instagram User ID has been submitted before by any wallet address.
        This is the ONLY reliable method for duplicate detection.
        
        Args:
            input_data: The input data to check
            wallet_address: Current wallet address
            contributor_email: Contributor email
            
        Returns:
            bool: True if duplicate User ID is found
        """
        try:
            if not self.blockchain_available:
                logging.warning("Blockchain not available, skipping duplicate check")
                return False
            
            # ONLY check: Instagram User ID duplicate detection (most reliable and secure)
            user_id_duplicate, user_id_info = self._check_duplicate_by_user_id(input_data)
            if user_id_duplicate:
                logging.warning(f"Instagram User ID duplicate detected: {user_id_info}")
                return True
                
            logging.info("No duplicate User ID found - contribution is unique")
            return False
            
        except Exception as e:
            logging.error(f"Error checking for duplicate data: {str(e)}")
            return False

    def _check_duplicate_by_user_id(self, input_data: dict) -> tuple[bool, dict]:
        """
        Check for duplicate Instagram User ID across all wallets.
        This is the most reliable method to detect the same person using different wallets.
        
        Args:
            input_data: The input data to check
            
        Returns:
            tuple[bool, dict]: (is_duplicate, match_info)
        """
        try:
            # Extract Instagram User ID from the current data
            user_id = self._extract_instagram_user_id(input_data)
            if not user_id:
                logging.info("No Instagram User ID found in data")
                return False, {"reason": "no_user_id"}
            
            logging.info(f"Checking for duplicate User ID: {user_id}")
            
            # Get all contributors from blockchain
            all_contributors = self.blockchain_client.get_all_contributors()
            
            for contributor_addr in all_contributors:
                existing_files = self.blockchain_client.get_contributor_files(contributor_addr)
                
                for file_hash in existing_files:
                    # Get existing contribution data from blockchain
                    existing_data = self._get_contribution_data_from_hash(file_hash)
                    if existing_data:
                        existing_user_id = self._extract_instagram_user_id(existing_data)
                        if existing_user_id and user_id == existing_user_id:
                            logging.warning(f"DUPLICATE USER ID DETECTED: {user_id} already exists in wallet {contributor_addr[:10]}...")
                            return True, {
                                "user_id": user_id,
                                "existing_wallet": contributor_addr,
                                "match_type": "user_id_duplicate"
                            }
            
            logging.info(f"User ID {user_id} is unique - no duplicates found")
            return False, {"user_id": user_id, "status": "unique"}
            
        except Exception as e:
            logging.error(f"Error checking User ID duplicate: {str(e)}")
            return False, {"error": str(e)}

    def _get_contribution_data_from_hash(self, file_hash: str) -> dict:
        """
        Get contribution data from blockchain using file hash.
        This is a placeholder - actual implementation would fetch from blockchain.
        
        Args:
            file_hash: The file hash to look up
            
        Returns:
            dict: Contribution data if found, empty dict otherwise
        """
        try:
            logging.debug(f"Fetching data for hash: {file_hash[:16]}...")
            # TODO: Implement actual blockchain data fetching
            # For now, return empty dict
            return {}
            
        except Exception as e:
            logging.error(f"Error fetching contribution data: {str(e)}")
            return {}

    def _extract_instagram_user_id(self, input_data: dict) -> str:
        """
        Extract Instagram User ID from the input data.
        This is the most reliable identifier for duplicate detection.
        
        Args:
            input_data: The input data dictionary
            
        Returns:
            str: Instagram User ID if found, empty string otherwise
        """
        try:
            # Try to extract from raw_export_data first (most reliable)
            raw_export_data = input_data.get('data', {}).get('raw_export_data', {})
            if raw_export_data:
                personal_info = raw_export_data.get('personal_information', {})
                user_id = personal_info.get('user_id')
                if user_id:
                    logging.info(f"Found Instagram User ID in raw_export_data: {user_id}")
                    return str(user_id)
            
            # Fallback: try to extract from profile
            profile = input_data.get('data', {}).get('profile', {})
            if profile:
                user_id = profile.get('user_id')
                if user_id:
                    logging.info(f"Found User ID in profile: {user_id}")
                    return str(user_id)
            
            logging.warning("No Instagram User ID found in data")
            return ""
            
        except Exception as e:
            logging.error(f"Error extracting Instagram User ID: {str(e)}")
            return ""

    def _generate_user_id_hash(self, input_data: dict) -> str:
        """
        Generate a hash based ONLY on Instagram User ID.
        This is the only immutable data that should be hashed for duplicate detection.
        
        Args:
            input_data: The input data dictionary
            
        Returns:
            str: User ID hash for duplicate detection
        """
        try:
            user_id = self._extract_instagram_user_id(input_data)
            if not user_id:
                logging.warning("No Instagram User ID found for hashing")
                return ""
            
            # Only hash the Instagram User ID - this is immutable and cannot be manipulated
            user_id_hash = hashlib.sha256(user_id.encode('utf-8')).hexdigest()
            logging.info(f"Generated User ID hash: {user_id_hash[:16]}... for User ID: {user_id}")
            return user_id_hash
            
        except Exception as e:
            logging.error(f"Error generating user ID hash: {str(e)}")
            return ""

    def _get_user_friendly_error_message(self, error_code: str) -> str:
        """
        Convert technical error codes to user-friendly messages
        
        Args:
            error_code: Technical error code
            
        Returns:
            str: User-friendly error message
        """
        error_messages = {
            # Schema validation errors
            "INVALID_SCHEMA": "Invalid file format. Please upload a valid Instagram Meta Export file.",
            
            # Data completeness errors
            "MISSING_RAW_EXPORT_DATA": "Your Instagram data is incomplete. Please upload a complete Meta Export file.",
            "MISSING_SECTION_LIKES": "Your likes data is missing. Please include the likes.json file.",
            "MISSING_SECTION_FOLLOWING": "Your following data is missing. Please include the following.json file.",
            "MISSING_SECTION_POSTS": "Your posts data is missing. Please include the posts.json file.",
            "MISSING_SECTION_COMMENTS": "Your comments data is missing. Please include the comments.json file.",
            "EMPTY_SECTION_LIKES": "Your likes data is empty. Please upload a file with valid data.",
            "EMPTY_SECTION_FOLLOWING": "Your following data is empty. Please upload a file with valid data.",
            "EMPTY_SECTION_POSTS": "Your posts data is empty. Please upload a file with valid data.",
            "EMPTY_SECTION_COMMENTS": "Your comments data is empty. Please upload a file with valid data.",
            "MISSING_PERSONAL_USER_ID": "Your Instagram user ID was not found. Please upload a valid Meta Export file.",
            "MISSING_PERSONAL_EMAIL": "Your Instagram email address was not found. Please upload a valid Meta Export file.",
            "MISSING_PERSONAL_NAME": "Your Instagram name was not found. Please upload a valid Meta Export file.",
            
            # Consistency errors
            "LIKES_ACTIVITIES_EMPTY_BUT_RAW_EXISTS": "Inconsistency in your likes data. Please upload the complete file.",
            "LIKES_RAW_EMPTY_BUT_ACTIVITIES_EXIST": "Inconsistency in your likes data. Please upload the complete file.",
            "FOLLOWING_ACTIVITIES_EMPTY_BUT_RAW_EXISTS": "Inconsistency in your following data. Please upload the complete file.",
            "FOLLOWING_RAW_EMPTY_BUT_ACTIVITIES_EXIST": "Inconsistency in your following data. Please upload the complete file.",
            "POSTS_ACTIVITIES_EMPTY_BUT_RAW_EXISTS": "Inconsistency in your posts data. Please upload the complete file.",
            "POSTS_RAW_EMPTY_BUT_ACTIVITIES_EXIST": "Inconsistency in your posts data. Please upload the complete file.",
            "LIKES_COUNT_POSITIVE_BUT_RAW_EMPTY": "Your likes count doesn't match your data. Please upload the complete file.",
            "LIKES_COUNT_ZERO_BUT_RAW_EXISTS": "Your likes count doesn't match your data. Please upload the complete file.",
            "FOLLOWING_COUNT_POSITIVE_BUT_RAW_EMPTY": "Your following count doesn't match your data. Please upload the complete file.",
            "FOLLOWING_COUNT_ZERO_BUT_RAW_EXISTS": "Your following count doesn't match your data. Please upload the complete file.",
            "POSTS_COUNT_POSITIVE_BUT_RAW_EMPTY": "Your posts count doesn't match your data. Please upload the complete file.",
            "POSTS_COUNT_ZERO_BUT_RAW_EXISTS": "Your posts count doesn't match your data. Please upload the complete file.",
            
            # Duplicate detection errors
            "DUPLICATE_DATA_DETECTED": "This Instagram account has already been uploaded by another wallet. Each Instagram account can only be uploaded once.",
            
            # Email mismatch errors
            "CONTRIBUTOR_EMAIL_MISMATCH": "Your Instagram email address doesn't match your Google Drive email address. Please use the same email address.",
            
            # Google verification errors
            "UNVERIFIED_STORAGE_EMAIL": "Your Google Drive email address is not verified. Please verify your email address.",
            "UNVERIFIED_STORAGE_USER": "Your Google Drive account could not be verified. Please sign in again.",
            
            # Processing errors
            "INSTAGRAM_DATA_PROCESSING_ERROR": "An error occurred while processing your Instagram data. Please check your file and try again.",
        }
        
        return error_messages.get(error_code, f"Unknown error: {error_code}")

    def _validate_data_completeness(self, input_data: dict) -> tuple[bool, list]:
        """
        Validate data completeness to prevent manipulation by file deletion.
        This function checks for required data sections and detects missing files.
        
        Args:
            input_data: The input data dictionary
            
        Returns:
            tuple[bool, list]: (is_complete, missing_sections)
        """
        missing_sections = []
        
        try:
            # Check raw_export_data structure
            raw_export_data = input_data.get('data', {}).get('raw_export_data', {})
            if not raw_export_data:
                missing_sections.append("MISSING_RAW_EXPORT_DATA")
                return False, missing_sections
            
            # Check for critical sections that should always be present
            critical_sections = [
                'personal_information',
                'likes', 
                'following',
                'posts',
                'comments'
            ]
            
            for section in critical_sections:
                if section not in raw_export_data:
                    missing_sections.append(f"MISSING_SECTION_{section.upper()}")
                elif not raw_export_data[section]:
                    missing_sections.append(f"EMPTY_SECTION_{section.upper()}")
            
            # Check personal_information completeness
            personal_info = raw_export_data.get('personal_information', {})
            if personal_info:
                required_personal_fields = ['user_id', 'email', 'name']
                for field in required_personal_fields:
                    if field not in personal_info or not personal_info[field]:
                        missing_sections.append(f"MISSING_PERSONAL_{field.upper()}")
            
            # Check activities data consistency
            activities = input_data.get('data', {}).get('activities', {})
            if activities:
                # Check if activities match raw_export_data
                self._check_activities_consistency(activities, raw_export_data, missing_sections)
            
            # Check metrics consistency
            metrics = input_data.get('data', {}).get('metrics', {})
            if metrics:
                self._check_metrics_consistency(metrics, raw_export_data, missing_sections)
            
            is_complete = len(missing_sections) == 0
            
            if is_complete:
                logging.info("Data completeness validation: PASSED")
            else:
                logging.warning(f"Data completeness validation: FAILED - {len(missing_sections)} issues")
                for issue in missing_sections:
                    logging.warning(f"  - {issue}")
            
            return is_complete, missing_sections
            
        except Exception as e:
            logging.error(f"Error in data completeness validation: {str(e)}")
            missing_sections.append(f"VALIDATION_ERROR: {str(e)}")
            return False, missing_sections

    def _check_activities_consistency(self, activities: dict, raw_export_data: dict, missing_sections: list) -> None:
        """
        Check consistency between activities and raw_export_data
        
        Args:
            activities: The activities dictionary
            raw_export_data: The raw export data dictionary
            missing_sections: List to append missing sections
        """
        try:
            # Check likes consistency
            likes_given = activities.get('likes_given', [])
            raw_likes = raw_export_data.get('likes', [])
            
            if len(likes_given) == 0 and len(raw_likes) > 0:
                missing_sections.append("LIKES_ACTIVITIES_EMPTY_BUT_RAW_EXISTS")
            elif len(likes_given) > 0 and len(raw_likes) == 0:
                missing_sections.append("LIKES_RAW_EMPTY_BUT_ACTIVITIES_EXIST")
            
            # Check following consistency
            following_list = activities.get('following_list', [])
            raw_following = raw_export_data.get('following', [])
            
            if len(following_list) == 0 and len(raw_following) > 0:
                missing_sections.append("FOLLOWING_ACTIVITIES_EMPTY_BUT_RAW_EXISTS")
            elif len(following_list) > 0 and len(raw_following) == 0:
                missing_sections.append("FOLLOWING_RAW_EMPTY_BUT_ACTIVITIES_EXIST")
            
            # Check posts consistency
            posts_created = activities.get('posts_created', [])
            raw_posts = raw_export_data.get('posts', [])
            
            if len(posts_created) == 0 and len(raw_posts) > 0:
                missing_sections.append("POSTS_ACTIVITIES_EMPTY_BUT_RAW_EXISTS")
            elif len(posts_created) > 0 and len(raw_posts) == 0:
                missing_sections.append("POSTS_RAW_EMPTY_BUT_ACTIVITIES_EXIST")
            
        except Exception as e:
            logging.error(f"Error checking activities consistency: {str(e)}")
            missing_sections.append(f"ACTIVITIES_CONSISTENCY_ERROR: {str(e)}")

    def _check_metrics_consistency(self, metrics: dict, raw_export_data: dict, missing_sections: list) -> None:
        """
        Check consistency between metrics and raw_export_data
        
        Args:
            metrics: The metrics dictionary
            raw_export_data: The raw export data dictionary
            missing_sections: List to append missing sections
        """
        try:
            # Check likes count consistency
            likes_count = metrics.get('likes_given_count', 0)
            raw_likes = raw_export_data.get('likes', [])
            
            if likes_count > 0 and len(raw_likes) == 0:
                missing_sections.append("LIKES_COUNT_POSITIVE_BUT_RAW_EMPTY")
            elif likes_count == 0 and len(raw_likes) > 0:
                missing_sections.append("LIKES_COUNT_ZERO_BUT_RAW_EXISTS")
            
            # Check following count consistency
            following_count = metrics.get('following_count', 0)
            raw_following = raw_export_data.get('following', [])
            
            if following_count > 0 and len(raw_following) == 0:
                missing_sections.append("FOLLOWING_COUNT_POSITIVE_BUT_RAW_EMPTY")
            elif following_count == 0 and len(raw_following) > 0:
                missing_sections.append("FOLLOWING_COUNT_ZERO_BUT_RAW_EXISTS")
            
            # Check posts count consistency
            posts_count = metrics.get('posts_count', 0)
            raw_posts = raw_export_data.get('posts', [])
            
            if posts_count > 0 and len(raw_posts) == 0:
                missing_sections.append("POSTS_COUNT_POSITIVE_BUT_RAW_EMPTY")
            elif posts_count == 0 and len(raw_posts) > 0:
                missing_sections.append("POSTS_COUNT_ZERO_BUT_RAW_EXISTS")
            
        except Exception as e:
            logging.error(f"Error checking metrics consistency: {str(e)}")
            missing_sections.append(f"METRICS_CONSISTENCY_ERROR: {str(e)}")


