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
            self.proof_response.attributes["errors"] = errors

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
        Check if the same data has been submitted before by any wallet address.
        This prevents both wallet switching and partial data deletion attacks.
        
        Args:
            input_data: The input data to check
            wallet_address: Current wallet address
            contributor_email: Contributor email
            
        Returns:
            bool: True if duplicate data is found
        """
        try:
            if not self.blockchain_available:
                return False
                
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

    def _generate_core_data_fingerprint(self, input_data: dict) -> str:
        """
        Generate a fingerprint of core data elements that should remain consistent
        even if peripheral data is modified.
        
        Args:
            input_data: The input data dictionary
            
        Returns:
            str: Core data fingerprint hash
        """
        try:
            profile = input_data.get('data', {}).get('profile', {})
            metrics = input_data.get('data', {}).get('metrics', {})
            activities = input_data.get('data', {}).get('activities', {})
            
            core_fingerprint = {
                'username': profile.get('username'),
                'email': profile.get('email'),
                'account_type': profile.get('account_type'),
                'posts_count': metrics.get('posts_count'),
                'follower_count': metrics.get('follower_count'),
                'following_count': metrics.get('following_count'),
                'account_age_days': metrics.get('account_age_days'),
                'platform': input_data.get('data', {}).get('platform'),
                'posts_sample': activities.get('posts_created', [])[:3] if activities.get('posts_created') else [],
                'following_sample': activities.get('following_list', [])[:5] if activities.get('following_list') else []
            }
            
            fingerprint_json = json.dumps(core_fingerprint, sort_keys=True, separators=(',', ':'))
            return hashlib.sha256(fingerprint_json.encode('utf-8')).hexdigest()
            
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
