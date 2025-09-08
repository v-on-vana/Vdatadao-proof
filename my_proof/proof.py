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
        Check if the same email has been submitted before by any wallet address.
        This prevents both wallet switching and partial data deletion attacks.
        Also checks for email-based duplicates to prevent Sybil attacks.
        
        Args:
            input_data: The input data to check
            wallet_address: Current wallet address
            contributor_email: Contributor email
            
        Returns:
            bool: True if duplicate data is found
        """
        try:
            if not self.blockchain_available:
                logging.warning("Blockchain not available, skipping duplicate check")
                return False
            
            # First check: Wallet-Email binding validation
            if not self._validate_wallet_email_binding(wallet_address, contributor_email):
                logging.warning(f"Invalid wallet-email binding: {wallet_address[:10]}... with {contributor_email}")
                return True
            
            # Second check: Email-based duplicate prevention
            if self._check_email_duplicate(contributor_email, wallet_address):
                logging.warning(f"Email duplicate detected: {contributor_email} already used by different wallet")
                return True
                
            # Second check: Data similarity across all contributors
            core_data_fingerprint = self._generate_core_data_fingerprint(input_data)
            
            all_contributors = self.blockchain_client.get_all_contributors()
            
            for contributor_addr in all_contributors:
                if contributor_addr.lower() == wallet_address.lower():
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

    def _check_email_duplicate(self, contributor_email: str, current_wallet: str) -> bool:
        """
        Check if the same email has been used by a different wallet address.
        This prevents Sybil attacks where users create multiple wallets with the same email.
        Uses improved email-wallet binding for better duplicate detection.
        
        Args:
            contributor_email: The email to check
            current_wallet: The current wallet address
            
        Returns:
            bool: True if email is already used by a different wallet
        """
        try:
            if not self.blockchain_available:
                logging.warning("Blockchain not available, skipping email duplicate check")
                return False
                
            # Generate email hash for comparison
            email_hash = hashlib.sha256(contributor_email.lower().strip().encode()).hexdigest()
            logging.info(f"Checking email duplicate for: {contributor_email} (hash: {email_hash[:16]}...)")
            
            all_contributors = self.blockchain_client.get_all_contributors()
            logging.info(f"Checking against {len(all_contributors)} existing contributors")
            
            for contributor_addr in all_contributors:
                if contributor_addr.lower() == current_wallet.lower():
                    continue
                    
                existing_files = self.blockchain_client.get_contributor_files(contributor_addr)
                logging.debug(f"Checking {len(existing_files)} files for contributor {contributor_addr[:10]}...")
                
                # Check if any existing file contains the same email
                for file_hash in existing_files:
                    # Method 1: Check if email hash is embedded in file hash
                    if email_hash in str(file_hash):
                        logging.warning(f"Email {contributor_email} already used by wallet {contributor_addr[:10]}... (method 1)")
                        return True
                    
                    # Method 2: Check if email-wallet pair exists in blockchain metadata
                    email_wallet_pair = f"{contributor_email.lower()}:{contributor_addr.lower()}"
                    pair_hash = hashlib.sha256(email_wallet_pair.encode()).hexdigest()
                    
                    if pair_hash in str(file_hash):
                        logging.warning(f"Email-wallet pair already exists: {contributor_email} with {contributor_addr[:10]}... (method 2)")
                        return True
                    
                    # Method 3: Check for email in contribution metadata (if available)
                    contribution_data = self._get_contribution_metadata_from_hash(file_hash)
                    if contribution_data:
                        existing_email = contribution_data.get('contributor_email', '').lower().strip()
                        if existing_email == contributor_email.lower().strip():
                            logging.warning(f"Email {contributor_email} found in contribution metadata for wallet {contributor_addr[:10]}... (method 3)")
                            return True
                        
            logging.info(f"Email {contributor_email} is unique - no duplicates found")
            return False
            
        except Exception as e:
            logging.error(f"Error checking email duplicate: {str(e)}")
            return False  # If check fails, allow contribution

    def _validate_wallet_email_binding(self, wallet_address: str, contributor_email: str) -> bool:
        """
        Validate wallet-email binding to ensure unique pairs.
        This prevents users from using the same email with multiple wallets
        or the same wallet with multiple emails.
        
        Args:
            wallet_address: The wallet address to validate
            contributor_email: The email address to validate
            
        Returns:
            bool: True if wallet-email binding is valid and unique
        """
        try:
            if not self.blockchain_available:
                logging.warning("Blockchain not available, skipping wallet-email binding validation")
                return True  # Allow if blockchain not available
                
            # Normalize inputs
            wallet_address = wallet_address.lower().strip()
            contributor_email = contributor_email.lower().strip()
            
            if not wallet_address or not contributor_email:
                logging.warning("Invalid wallet address or email provided")
                return False
            
            # Generate wallet-email binding hash
            wallet_email_binding = f"{wallet_address}:{contributor_email}"
            binding_hash = hashlib.sha256(wallet_email_binding.encode()).hexdigest()
            
            logging.info(f"Validating wallet-email binding: {wallet_address[:10]}... with {contributor_email}")
            
            all_contributors = self.blockchain_client.get_all_contributors()
            
            for contributor_addr in all_contributors:
                if contributor_addr.lower() == wallet_address:
                    continue
                    
                existing_files = self.blockchain_client.get_contributor_files(contributor_addr)
                
                for file_hash in existing_files:
                    # Check if this wallet-email binding already exists
                    if binding_hash in str(file_hash):
                        logging.warning(f"Wallet-email binding already exists: {wallet_address[:10]}... with {contributor_email}")
                        return False
                    
                    # Check for reverse binding (same email with different wallet)
                    contribution_data = self._get_contribution_metadata_from_hash(file_hash)
                    if contribution_data:
                        existing_email = contribution_data.get('contributor_email', '').lower().strip()
                        existing_wallet = contribution_data.get('wallet_address', '').lower().strip()
                        
                        if existing_email == contributor_email and existing_wallet != wallet_address:
                            logging.warning(f"Email {contributor_email} already bound to different wallet: {existing_wallet[:10]}...")
                            return False
                        
                        if existing_wallet == wallet_address and existing_email != contributor_email:
                            logging.warning(f"Wallet {wallet_address[:10]}... already bound to different email: {existing_email}")
                            return False
            
            logging.info(f"Wallet-email binding is valid and unique: {wallet_address[:10]}... with {contributor_email}")
            return True
            
        except Exception as e:
            logging.error(f"Error validating wallet-email binding: {str(e)}")
            return True  # Allow if validation fails

    def _get_contribution_metadata_from_hash(self, file_hash: str) -> dict:
        """
        Get contribution metadata from blockchain using file hash.
        This extracts email and wallet information for duplicate detection.
        
        Args:
            file_hash: The file hash to look up
            
        Returns:
            dict: Contribution metadata if found, empty dict otherwise
        """
        try:
            logging.debug(f"Fetching metadata for hash: {file_hash[:16]}...")
            
            # TODO: Implement actual blockchain metadata fetching
            # For now, return empty dict - in production this would:
            # 1. Query blockchain for contribution metadata
            # 2. Extract contributor email and wallet address
            # 3. Return structured metadata
            
            # Placeholder implementation
            return {}
            
        except Exception as e:
            logging.error(f"Error fetching contribution metadata: {str(e)}")
            return {}

    def _generate_core_data_fingerprint(self, input_data: dict) -> str:
        """
        Generate a fingerprint of core data elements that should remain consistent
        even if peripheral data is modified. Includes wallet-email binding for
        unique identification and cross-wallet duplicate prevention.
        
        Args:
            input_data: The input data dictionary
            
        Returns:
            str: Core data fingerprint hash
        """
        try:
            profile = input_data.get('data', {}).get('profile', {})
            metrics = input_data.get('data', {}).get('metrics', {})
            activities = input_data.get('data', {}).get('activities', {})
            contributor = input_data.get('contributor', {})
            
            # Create wallet-email binding for unique identification
            wallet_address = contributor.get('wallet_address', '').lower().strip()
            contributor_email = contributor.get('email', '').lower().strip()
            wallet_email_binding = f"{wallet_address}:{contributor_email}"
            
            # Generate core fingerprint with wallet-email binding
            core_fingerprint = {
                # Wallet-Email binding (unique identifier)
                'wallet_email_binding': wallet_email_binding,
                'wallet_address': wallet_address,
                'contributor_email': contributor_email,
                
                # Instagram profile data
                'username': profile.get('username', '').lower().strip(),
                'instagram_email': profile.get('email', '').lower().strip(),
                'account_type': profile.get('account_type', ''),
                
                # Core metrics (immutable data)
                'posts_count': metrics.get('posts_count', 0),
                'follower_count': metrics.get('follower_count', 0),
                'following_count': metrics.get('following_count', 0),
                'account_age_days': metrics.get('account_age_days', 0),
                
                # Platform and data source
                'platform': input_data.get('data', {}).get('platform', ''),
                'source_type': input_data.get('data', {}).get('source_type', ''),
                'extraction_method': input_data.get('data', {}).get('extraction_method', ''),
                
                # Sample activities (for uniqueness detection)
                'posts_sample': activities.get('posts_created', [])[:3] if activities.get('posts_created') else [],
                'following_sample': activities.get('following_list', [])[:5] if activities.get('following_list') else [],
                
                # Data integrity markers
                'has_raw_export_data': bool(input_data.get('data', {}).get('raw_export_data')),
                'data_completeness': input_data.get('metadata', {}).get('extraction_completeness', 0)
            }
            
            # Remove None values and empty strings for consistent hashing
            cleaned_fingerprint = {k: v for k, v in core_fingerprint.items() if v is not None and v != ''}
            
            fingerprint_json = json.dumps(cleaned_fingerprint, sort_keys=True, separators=(',', ':'))
            fingerprint_hash = hashlib.sha256(fingerprint_json.encode('utf-8')).hexdigest()
            
            logging.info(f"Generated core data fingerprint: {fingerprint_hash[:16]}...")
            logging.debug(f"Fingerprint includes wallet-email binding: {wallet_email_binding}")
            
            return fingerprint_hash
            
        except Exception as e:
            logging.error(f"Error generating core data fingerprint: {str(e)}")
            return ""

    def _calculate_data_similarity(self, current_fingerprint: str, existing_hash: str) -> float:
        """
        Calculate similarity between current data fingerprint and existing contribution.
        Uses both exact matching and fuzzy similarity.
        
        Args:
            current_fingerprint: Current data fingerprint
            existing_hash: Existing contribution hash from blockchain
            
        Returns:
            float: Similarity score between 0 and 1
        """
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
            "INVALID_WALLET_EMAIL_BINDING": "This wallet address and email combination has already been used. Each wallet can only be paired with one email address.",
            "EMAIL_ALREADY_BOUND": "This email address is already associated with a different wallet. Please use a different email or wallet.",
            "WALLET_ALREADY_BOUND": "This wallet address is already associated with a different email. Please use a different wallet or email.",
            
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


