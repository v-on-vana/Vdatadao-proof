import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from my_proof.models.proof_response import ProofResponse
from my_proof.models.instagram import InstagramData
from my_proof.utils.blockchain import BlockchainClient
from my_proof.utils.google import get_google_user
from my_proof.utils.schema import validate_schema, detect_data_type, get_schema_requirements
from my_proof.config import settings


class Proof:
    def __init__(self):
        self.proof_response = ProofResponse(dlp_id=settings.DLP_ID)
        try:
            self.blockchain_client = BlockchainClient()
            self.blockchain_available = True
        except Exception as e:
            logging.warning(f"Blockchain client initialization failed: {str(e)}")
            self.blockchain_available = False

    def generate(self) -> ProofResponse:
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

        if self.blockchain_available and settings.OWNER_ADDRESS:
            existing_file_count = self.blockchain_client.get_contributor_file_count()
            if existing_file_count > 0:
                errors.append(f"DUPLICATE_CONTRIBUTION")
        else:
            logging.info("Skipping blockchain validation")

        for input_filename in os.listdir(settings.INPUT_DIR):
            logging.info(f"Checking file: {input_filename}")
            input_file = os.path.join(settings.INPUT_DIR, input_filename)

            if os.path.splitext(input_file)[1].lower() == '.json':
                with open(input_file, 'r', encoding='utf-8') as f:
                    json_content = f.read()
                    logging.info(f"Validating file: {json_content[:50]}...")
                    input_data = json.loads(json_content)
                    
                    data_type = detect_data_type(input_data)
                    schema_type, schema_matches = validate_schema(input_data)
                    
                    if not schema_matches:
                        errors.append(f"INVALID_SCHEMA")
                        break
                    
                    if data_type == 'instagram':
                        self._process_instagram_data(input_data, google_user, errors)
                    elif data_type == 'google':
                        self._process_google_data(input_data, google_user, errors)
                    else:
                        errors.append("UNKNOWN_DATA_TYPE")
                        break
                    
                    self.proof_response.metadata = {
                        'schema_type': schema_type,
                        'data_type': data_type,
                        'processing_timestamp': datetime.now().isoformat()
                    }
                    
                    self.proof_response.valid = len(errors) == 0
        
        if len(errors) > 0:
            self.proof_response.attributes['errors'] = errors

        return self.proof_response

    def _process_instagram_data(self, input_data: Dict[str, Any], google_user, errors: List[str]):
        try:
            instagram_data = InstagramData(**input_data)
            
            quality_score = self._calculate_instagram_quality(instagram_data)
            authenticity_score = self._calculate_instagram_authenticity(instagram_data, google_user)
            uniqueness_score = self._calculate_instagram_uniqueness(instagram_data)
            ownership_score = 1.0 if settings.OWNER_ADDRESS else 0.0
            
            self.proof_response.quality = quality_score
            self.proof_response.authenticity = authenticity_score
            self.proof_response.uniqueness = uniqueness_score
            self.proof_response.ownership = ownership_score
            
            self.proof_response.score = (
                self.proof_response.quality * 0.35 + 
                self.proof_response.authenticity * 0.30 + 
                self.proof_response.uniqueness * 0.25 + 
                self.proof_response.ownership * 0.10
            )
            
            self.proof_response.attributes = {
                'data_type': 'instagram',
                'username': instagram_data.username,
                'profile_verified': instagram_data.profile.isVerified,
                'profile_private': instagram_data.profile.isPrivate,
                'follower_count': instagram_data.profile.followerCount,
                'following_count': instagram_data.profile.followingCount,
                'post_count': instagram_data.profile.postCount,
                'posts_analyzed': len(instagram_data.posts or []),
                'stories_analyzed': len(instagram_data.stories or []),
                'reels_analyzed': len(instagram_data.reels or []),
                'has_analytics': instagram_data.analytics is not None,
                'export_source': instagram_data.metadata.source,
                'quality_breakdown': self._get_quality_breakdown(instagram_data),
                'verified_with_oauth': google_user is not None
            }
            
        except Exception as e:
            logging.error(f"Error processing Instagram data: {str(e)}")
            errors.append("INSTAGRAM_PROCESSING_ERROR")

    def _process_google_data(self, input_data: Dict[str, Any], google_user, errors: List[str]):
        if google_user:
            profile_matches = self._verify_profile_match(google_user, input_data)
            if not profile_matches:
                errors.append("PROFILE_MISMATCH")
                logging.error(f"Input profile data does not match Google profile")
        
        self.proof_response.ownership = 1.0 if settings.OWNER_ADDRESS else 0.0
        self.proof_response.quality = 1.0
        self.proof_response.authenticity = 1.0 if google_user else 0.0
        self.proof_response.uniqueness = 1.0

        self.proof_response.score = (
            self.proof_response.quality * 0.4 + 
            self.proof_response.authenticity * 0.3 + 
            self.proof_response.uniqueness * 0.2 + 
            self.proof_response.ownership * 0.1
        )

        self.proof_response.attributes = {
            'data_type': 'google',
            'user_email': input_data.get('email'),
            'user_id': input_data.get('userId'),
            'profile_name': input_data.get('profile', {}).get('name'),
            'verified_with_oauth': google_user is not None
        }

    def _calculate_instagram_quality(self, instagram_data: InstagramData) -> float:
        quality_factors = []
        
        profile_completeness = self._calculate_profile_completeness(instagram_data.profile)
        quality_factors.append(('profile_completeness', profile_completeness, 0.20))
        
        content_richness = self._calculate_content_richness(instagram_data)
        quality_factors.append(('content_richness', content_richness, 0.30))
        
        engagement_quality = self._calculate_engagement_quality(instagram_data)
        quality_factors.append(('engagement_quality', engagement_quality, 0.25))
        
        data_recency = self._calculate_data_recency(instagram_data)
        quality_factors.append(('data_recency', data_recency, 0.15))
        
        metadata_quality = self._calculate_metadata_quality(instagram_data.metadata)
        quality_factors.append(('metadata_quality', metadata_quality, 0.10))
        
        total_score = sum(score * weight for _, score, weight in quality_factors)
        
        logging.info(f"Instagram quality factors: {quality_factors}")
        logging.info(f"Total quality score: {total_score}")
        
        return min(1.0, max(0.0, total_score))

    def _calculate_profile_completeness(self, profile) -> float:
        factors = []
        
        factors.append(1.0 if profile.displayName else 0.0)
        factors.append(1.0 if profile.biography and len(profile.biography) > 10 else 0.0)
        factors.append(1.0 if profile.profilePictureUrl else 0.0)
        
        factors.append(1.0 if profile.followerCount > 0 else 0.0)
        factors.append(1.0 if profile.postCount > 0 else 0.0)
        
        factors.append(1.0 if profile.isVerified else 0.5)
        factors.append(1.0 if profile.externalUrl else 0.5)
        factors.append(1.0 if profile.category else 0.5)
        
        return sum(factors) / len(factors)

    def _calculate_content_richness(self, instagram_data: InstagramData) -> float:
        content_score = 0.0
        
        posts = instagram_data.posts or []
        if posts:
            posts_score = min(1.0, len(posts) / 10.0)
            
            media_types = set(post.mediaType for post in posts)
            variety_bonus = len(media_types) / 3.0
            
            caption_bonus = sum(1 for post in posts if post.caption and len(post.caption) > 10) / len(posts)
            hashtag_bonus = sum(1 for post in posts if post.hashtags and len(post.hashtags) > 0) / len(posts)
            
            posts_score = posts_score * (1 + variety_bonus + caption_bonus + hashtag_bonus) / 4
            content_score += posts_score * 0.5
        
        stories = instagram_data.stories or []
        if stories:
            stories_score = min(1.0, len(stories) / 20.0)
            content_score += stories_score * 0.3
        
        reels = instagram_data.reels or []
        if reels:
            reels_score = min(1.0, len(reels) / 5.0)
            
            original_audio_bonus = sum(1 for reel in reels 
                                     if reel.audioInfo and reel.audioInfo.get('isOriginal', False)) / len(reels)
            
            reels_score = reels_score * (1 + original_audio_bonus) / 2
            content_score += reels_score * 0.2
        
        return min(1.0, content_score)

    def _calculate_engagement_quality(self, instagram_data: InstagramData) -> float:
        posts = instagram_data.posts or []
        if not posts:
            return 0.5
        
        engagement_scores = []
        
        for post in posts:
            likes = post.likeCount or 0
            comments = post.commentCount or 0
            shares = post.shareCount or 0
            
            total_engagement = likes + (comments * 5) + (shares * 10)
            
            import math
            normalized_engagement = math.log(max(1, total_engagement)) / math.log(1000)
            engagement_scores.append(min(1.0, normalized_engagement))
        
        avg_engagement = sum(engagement_scores) / len(engagement_scores)
        
        engagement_variance = sum((score - avg_engagement) ** 2 for score in engagement_scores) / len(engagement_scores)
        consistency_bonus = 1.0 - min(1.0, engagement_variance * 10)
        
        return (avg_engagement + consistency_bonus) / 2

    def _calculate_data_recency(self, instagram_data: InstagramData) -> float:
        current_time = datetime.now().timestamp() * 1000
        export_time = instagram_data.exportTimestamp
        
        days_old = (current_time - export_time) / (1000 * 60 * 60 * 24)
        
        if days_old <= 7:
            return 1.0
        elif days_old <= 30:
            return 1.0 - (days_old - 7) / 23
        else:
            return max(0.1, 1.0 - days_old / 365)

    def _calculate_metadata_quality(self, metadata) -> float:
        quality_factors = []
        
        if metadata.source == 'instagram_official_export':
            quality_factors.append(1.0)
        elif metadata.source == 'instagram_api':
            quality_factors.append(0.8)
        else:
            quality_factors.append(0.6)
        
        file_count_score = min(1.0, metadata.fileCount / 10.0)
        quality_factors.append(file_count_score)
        
        media_size_score = min(1.0, (metadata.totalMediaSize or 0) / (100 * 1024 * 1024))
        quality_factors.append(media_size_score)
        
        return sum(quality_factors) / len(quality_factors)

    def _calculate_instagram_authenticity(self, instagram_data: InstagramData, google_user) -> float:
        authenticity_factors = []
        
        oauth_score = 1.0 if google_user else 0.0
        authenticity_factors.append(('oauth_verification', oauth_score, 0.40))
        
        verification_score = 1.0 if instagram_data.profile.isVerified else 0.5
        authenticity_factors.append(('instagram_verification', verification_score, 0.20))
        
        account_age_score = self._estimate_account_age_score(instagram_data)
        authenticity_factors.append(('account_age', account_age_score, 0.20))
        
        consistency_score = self._check_data_consistency(instagram_data)
        authenticity_factors.append(('data_consistency', consistency_score, 0.20))
        
        total_score = sum(score * weight for _, score, weight in authenticity_factors)
        
        logging.info(f"Instagram authenticity factors: {authenticity_factors}")
        
        return min(1.0, max(0.0, total_score))

    def _calculate_instagram_uniqueness(self, instagram_data: InstagramData) -> float:
        uniqueness_factors = []
        
        uniqueness_factors.append(1.0)
        
        posts = instagram_data.posts or []
        if posts:
            timestamps = [post.timestamp for post in posts]
            time_variety = len(set(ts // (24 * 60 * 60 * 1000) for ts in timestamps)) / max(1, len(timestamps))
            uniqueness_factors.append(time_variety)
            
            captions = [post.caption for post in posts if post.caption]
            if captions:
                unique_captions = len(set(captions)) / len(captions)
                uniqueness_factors.append(unique_captions)
        
        return sum(uniqueness_factors) / len(uniqueness_factors) if uniqueness_factors else 0.5

    def _estimate_account_age_score(self, instagram_data: InstagramData) -> float:
        posts = instagram_data.posts or []
        if not posts:
            return 0.5
        
        earliest_timestamp = min(post.timestamp for post in posts)
        current_time = datetime.now().timestamp() * 1000
        
        account_age_days = (current_time - earliest_timestamp) / (1000 * 60 * 60 * 24)
        
        if account_age_days > 365:
            return 1.0
        elif account_age_days > 90:
            return 0.8
        elif account_age_days > 30:
            return 0.6
        else:
            return 0.3

    def _check_data_consistency(self, instagram_data: InstagramData) -> float:
        consistency_factors = []
        
        declared_posts = instagram_data.profile.postCount
        actual_posts = len(instagram_data.posts or [])
        
        if declared_posts > 0:
            post_consistency = min(1.0, actual_posts / declared_posts)
            consistency_factors.append(post_consistency)
        
        posts = instagram_data.posts or []
        if posts:
            sorted_posts = sorted(posts, key=lambda p: p.timestamp, reverse=True)
            order_consistency = sum(1 for i, post in enumerate(posts) 
                                  if i < len(sorted_posts) and post.postId == sorted_posts[i].postId) / len(posts)
            consistency_factors.append(order_consistency)
        
        export_timestamp = instagram_data.exportTimestamp
        metadata_timestamp = datetime.fromisoformat(instagram_data.metadata.exportDate.replace('Z', '+00:00')).timestamp() * 1000
        
        timestamp_diff = abs(export_timestamp - metadata_timestamp) / (1000 * 60 * 60)
        timestamp_consistency = 1.0 if timestamp_diff < 24 else max(0.5, 1.0 - timestamp_diff / (24 * 7))
        consistency_factors.append(timestamp_consistency)
        
        return sum(consistency_factors) / len(consistency_factors) if consistency_factors else 0.5

    def _get_quality_breakdown(self, instagram_data: InstagramData) -> Dict[str, float]:
        return {
            'profile_completeness': self._calculate_profile_completeness(instagram_data.profile),
            'content_richness': self._calculate_content_richness(instagram_data),
            'engagement_quality': self._calculate_engagement_quality(instagram_data),
            'data_recency': self._calculate_data_recency(instagram_data),
            'metadata_quality': self._calculate_metadata_quality(instagram_data.metadata)
        }
        
    def _verify_profile_match(self, google_user, input_data):
        if input_data.get('userId') != google_user.id:
            logging.error(f"User ID mismatch: {input_data.get('userId')} != {google_user.id}")
            return False
            
        if input_data.get('email') != google_user.email:
            logging.error(f"Email mismatch: {input_data.get('email')} != {google_user.email}")
            return False
            
        profile_name = input_data.get('profile', {}).get('name')
        if profile_name and profile_name != google_user.name:
            logging.error(f"Name mismatch: {profile_name} != {google_user.name}")
            return False
            
        logging.info("Google profile verification successful")
        return True

