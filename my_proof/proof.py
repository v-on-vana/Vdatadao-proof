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

        # Fetch Google user info if token is provided
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

        # Get existing file count from blockchain if available
        if self.blockchain_available and settings.OWNER_ADDRESS:
            existing_file_count = self.blockchain_client.get_contributor_file_count()
            if existing_file_count > 0:
                errors.append(f"DUPLICATE_CONTRIBUTION")
        else:
            logging.info("Skipping blockchain validation")

        # Iterate through files and calculate data validity
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

                    # Process based on schema type
                    if schema_type == "instagram-meta-export.json":
                        self._process_instagram_data(
                            input_data, schema_matches, google_user, errors
                        )
                    else:
                        self._process_google_data(
                            input_data, schema_matches, google_user, errors
                        )

                    # Additional metadata about the proof, written onchain
                    self.proof_response.metadata = {
                        "schema_type": schema_type,
                    }

                    self.proof_response.valid = len(errors) == 0

        # Only include errors if there are any
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
        # Check userId matches Google user ID
        if input_data.get("userId") != google_user.id:
            logging.error(
                f"User ID mismatch: {input_data.get('userId')} != {google_user.id}"
            )
            return False

        # Check email matches Google email
        if input_data.get("email") != google_user.email:
            logging.error(
                f"Email mismatch: {input_data.get('email')} != {google_user.email}"
            )
            return False

        # Check profile name matches Google name if available
        profile_name = input_data.get("profile", {}).get("name")
        if profile_name and profile_name != google_user.name:
            logging.error(f"Name mismatch: {profile_name} != {google_user.name}")
            return False

        logging.info("Google profile verification successful")
        return True

    def _process_google_data(self, input_data, schema_matches, google_user, errors):
        """Process Google profile data and calculate scores."""
        # Verify the input data matches the Google profile
        if google_user:
            profile_matches = self._verify_profile_match(google_user, input_data)
            if not profile_matches:
                errors.append("PROFILE_MISMATCH")
                logging.error(f"Input profile data does not match Google profile")

        # Calculate proof-of-contribution scores
        self.proof_response.ownership = 1.0 if settings.OWNER_ADDRESS else 0.0
        self.proof_response.quality = 1.0 if schema_matches else 0.0
        self.proof_response.authenticity = (
            1.0 if google_user and schema_matches else 0.0
        )
        self.proof_response.uniqueness = 1.0

        # Calculate overall score
        self.proof_response.score = (
            self.proof_response.quality * 0.4
            + self.proof_response.authenticity * 0.3
            + self.proof_response.uniqueness * 0.2
            + self.proof_response.ownership * 0.1
        )

        # Additional (public) properties to include in the proof about the data
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
            # Validate data structure using Pydantic model
            instagram_data = InstagramContribution(**input_data)

            # Verify contributor email matches Google user if available
            if google_user:
                contributor_email = instagram_data.contributor.email
                if contributor_email != google_user.email:
                    errors.append("CONTRIBUTOR_EMAIL_MISMATCH")
                    logging.error(
                        f"Contributor email {contributor_email} does not match Google email {google_user.email}"
                    )

            # Calculate quality score based on data completeness and metrics
            quality_score = self._calculate_instagram_quality_score(instagram_data)

            # Calculate authenticity score based on verification and consistency
            authenticity_score = self._calculate_instagram_authenticity_score(
                instagram_data, google_user
            )

            # Calculate uniqueness score based on account activity and engagement
            uniqueness_score = self._calculate_instagram_uniqueness_score(
                instagram_data
            )

            # Ownership score
            ownership_score = 1.0 if settings.OWNER_ADDRESS else 0.0

            # Set individual scores
            self.proof_response.quality = quality_score
            self.proof_response.authenticity = authenticity_score
            self.proof_response.uniqueness = uniqueness_score
            self.proof_response.ownership = ownership_score

            # Calculate overall score with Instagram-specific weighting
            self.proof_response.score = (
                quality_score * 0.35
                + authenticity_score * 0.35
                + uniqueness_score * 0.20
                + ownership_score * 0.10
            )

            # Run AI detection for additional attributes
            ai_result = None
            try:
                ai_result = self.ai_detector.detect_ai_content(instagram_data.dict())
            except Exception as e:
                logging.error(f"AI detection for attributes failed: {str(e)}")

            # Additional attributes for Instagram data
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
            
            # Add AI detection results to attributes if available
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

            # Set default scores on error
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

        # Base score for valid schema (30%)
        score += 0.3

        # Metadata quality scores (40%)
        meta_score = (
            instagram_data.metadata.extraction_completeness / 100 * 0.2
            + instagram_data.metadata.quality_score / 100 * 0.1
            + instagram_data.metadata.data_freshness / 100 * 0.1
        )
        score += meta_score

        # Profile completeness (20%)
        profile_fields = [
            instagram_data.data.profile.username,
            instagram_data.data.profile.display_name,
            instagram_data.data.profile.email,
            instagram_data.data.profile.account_type,
        ]
        complete_fields = sum(1 for field in profile_fields if field)
        score += (complete_fields / len(profile_fields)) * 0.2

        # Activity data presence (10%)
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

        # Google OAuth verification (25%)
        if google_user:
            score += 0.25

        # Account verification indicators (20%)
        if instagram_data.data.profile.phone_confirmed:
            score += 0.10
        if instagram_data.data.profile.email:
            score += 0.10

        # Data consistency checks (15%)
        metrics = instagram_data.data.metrics
        if metrics.total_interactions == (
            metrics.likes_given_count + metrics.comments_count
        ):
            score += 0.075
        if metrics.account_age_days > 0:
            score += 0.075

        # Source verification (10%)
        if (
            instagram_data.data.source_type == "meta_export"
            and instagram_data.data.extraction_method == "google_drive_api"
        ):
            score += 0.10

        # AI Detection Analysis (30%)
        try:
            ai_result = self.ai_detector.detect_ai_content(instagram_data.dict())
            ai_confidence = ai_result.get('confidence', 0.0)
            
            # Inverse relationship: higher AI confidence = lower authenticity
            ai_authenticity_score = max(0.0, 1.0 - ai_confidence)
            score += ai_authenticity_score * 0.30
            
            # Log AI detection results for debugging
            if ai_result.get('is_ai_generated'):
                logging.warning(f"AI-generated content detected with confidence: {ai_confidence:.2f}")
                logging.warning(f"AI indicators: {ai_result.get('indicators', [])}")
            else:
                logging.info(f"Content appears authentic. AI confidence: {ai_confidence:.2f}")
                
        except Exception as e:
            logging.error(f"AI detection failed: {str(e)}")
            # If AI detection fails, don't penalize but don't add score either
            pass

        return min(score, 1.0)

    def _calculate_instagram_uniqueness_score(
        self, instagram_data: InstagramContribution
    ) -> float:
        """Calculate uniqueness score based on account activity and engagement."""
        score = 0.0
        metrics = instagram_data.data.metrics

        # Account age factor (25%)
        if metrics.account_age_days > 365:  # More than 1 year
            score += 0.25
        elif metrics.account_age_days > 30:  # More than 1 month
            score += 0.15
        elif metrics.account_age_days > 0:
            score += 0.05

        # Content creation activity (35%)
        if metrics.posts_count > 100:
            score += 0.35
        elif metrics.posts_count > 50:
            score += 0.25
        elif metrics.posts_count > 10:
            score += 0.15
        elif metrics.posts_count > 0:
            score += 0.05

        # Social engagement (25%)
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

        # Network size (15%)
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
