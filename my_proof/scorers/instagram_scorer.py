import logging
from typing import Dict, Any, Optional

from my_proof.scorers.base_scorer import BaseScorer
from my_proof.models.instagram import InstagramContribution
from my_proof.utils.ai_detector import AIDetector
from my_proof.config import settings

class InstagramScorer(BaseScorer):
    
    def __init__(self):
        self.ai_detector = AIDetector()
    
    def calculate_quality_score(self, instagram_data: InstagramContribution) -> float:
        score = 0.0

        score += 0.10

        meta_score = (
            instagram_data.metadata.extraction_completeness / 100 * 0.15
            + instagram_data.metadata.quality_score / 100 * 0.10
            + instagram_data.metadata.data_freshness / 100 * 0.05
        )
        score += meta_score

        profile_fields = [
            instagram_data.data.profile.username,
            instagram_data.data.profile.display_name,
            instagram_data.data.profile.email,
            instagram_data.data.profile.account_type,
        ]
        complete_fields = sum(1 for field in profile_fields if field)
        score += (complete_fields / len(profile_fields)) * 0.15

        metrics = instagram_data.data.metrics
        
        activity_score = self._calculate_activity_quality_score(metrics, instagram_data.data.activities)
        score += activity_score * 0.25

        engagement_score = self._calculate_engagement_quality_score(metrics)
        score += engagement_score * 0.20

        content_depth_score = self._calculate_content_depth_score(instagram_data.data.activities)
        score += content_depth_score * 0.15

        return min(score, 1.0)

    def _calculate_activity_quality_score(self, metrics, activities) -> float:
        activity_score = 0.0
        
        if metrics.posts_count > 50:
            activity_score += 0.4
        elif metrics.posts_count > 20:
            activity_score += 0.3
        elif metrics.posts_count > 5:
            activity_score += 0.2
        elif metrics.posts_count > 0:
            activity_score += 0.1

        if len(activities.following_list) > 0:
            activity_score += 0.2
        if len(activities.likes_given) > 0:
            activity_score += 0.2
        if len(activities.comments_made) > 0:
            activity_score += 0.2
        
        return min(activity_score, 1.0)

    def _calculate_engagement_quality_score(self, metrics) -> float:
        engagement_score = 0.0
        
        total_activity = metrics.posts_count + metrics.likes_given_count + metrics.comments_count
        if total_activity == 0:
            return 0.0

        if metrics.follower_count == 0:
            engagement_score = 0.1
        elif metrics.follower_count > 0 and metrics.posts_count > 0:
            follower_to_post_ratio = metrics.follower_count / metrics.posts_count
            if follower_to_post_ratio > 10:
                engagement_score += 0.4
            elif follower_to_post_ratio > 5:
                engagement_score += 0.3
            elif follower_to_post_ratio > 1:
                engagement_score += 0.2
            else:
                engagement_score += 0.15
        
        if metrics.account_age_days > 0:
            daily_activity = total_activity / metrics.account_age_days
            if daily_activity > 1:
                engagement_score += 0.2
            elif daily_activity > 0.1:
                engagement_score += 0.15
            elif daily_activity > 0.01:
                engagement_score += 0.1
            else:
                engagement_score += 0.05

        network_size = metrics.following_count + metrics.follower_count
        if network_size > 100:
            engagement_score += 0.2
        elif network_size > 50:
            engagement_score += 0.15
        elif network_size > 10:
            engagement_score += 0.1
        elif network_size > 0:
            engagement_score += 0.05

        return min(engagement_score, 1.0)

    def _calculate_content_depth_score(self, activities) -> float:
        depth_score = 0.0
        
        posts_with_titles = sum(1 for post in activities.posts_created if post.title)
        if posts_with_titles > 0:
            depth_score += 0.3

        photo_posts = sum(1 for post in activities.posts_created if post.has_photo)
        if photo_posts > 0:
            depth_score += 0.2

        diverse_interactions = 0
        if len(activities.posts_created) > 0:
            diverse_interactions += 1
        if len(activities.likes_given) > 0:
            diverse_interactions += 1
        if len(activities.comments_made) > 0:
            diverse_interactions += 1
        if len(activities.following_list) > 0:
            diverse_interactions += 1

        depth_score += (diverse_interactions / 4.0) * 0.5

        return min(depth_score, 1.0)

    def calculate_authenticity_score(self, instagram_data: InstagramContribution, google_user: Optional[Any] = None) -> float:
        score = 0.0

        if instagram_data.data.profile.phone_confirmed:
            score += 0.20
        if instagram_data.data.profile.email:
            score += 0.15

        metrics = instagram_data.data.metrics
        if metrics.total_interactions == (
            metrics.likes_given_count + metrics.comments_count
        ):
            score += 0.15
        if metrics.account_age_days > 0:
            score += 0.15

        if instagram_data.data.source_type == "meta_export":
            score += 0.25

        try:
            ai_result = self.ai_detector.detect_ai_content(instagram_data.dict())
            ai_confidence = ai_result.get('confidence', 0.0)
            
            ai_authenticity_score = max(0.0, 1.0 - ai_confidence)
            score += ai_authenticity_score * 0.10
            
            if ai_result.get('is_ai_generated'):
                logging.warning(f"AI-generated content detected with confidence: {ai_confidence:.2f}")
                logging.warning(f"AI indicators: {ai_result.get('indicators', [])}")
            else:
                logging.info(f"Content appears authentic. AI confidence: {ai_confidence:.2f}")
                
        except Exception as e:
            logging.error(f"AI detection failed: {str(e)}")
            pass

        return min(score, 1.0)

    def calculate_uniqueness_score(self, instagram_data: InstagramContribution) -> float:
        score = 0.0
        metrics = instagram_data.data.metrics

        age_score = self._calculate_account_age_uniqueness(metrics.account_age_days)
        score += age_score * 0.25

        activity_uniqueness = self._calculate_activity_uniqueness(metrics)
        score += activity_uniqueness * 0.35

        social_network_uniqueness = self._calculate_social_network_uniqueness(metrics)
        score += social_network_uniqueness * 0.25

        content_uniqueness = self._calculate_content_uniqueness(instagram_data.data.activities)
        score += content_uniqueness * 0.15

        return min(score, 1.0)

    def _calculate_account_age_uniqueness(self, account_age_days: int) -> float:
        if account_age_days > 7300:  # 20+ years - ULTRA RARE
            return 1.0
        elif account_age_days > 3650:  # 10+ years - VERY RARE
            return 0.95
        elif account_age_days > 1825:  # 5+ years - RARE
            return 0.8
        elif account_age_days > 730:   # 2+ years
            return 0.6
        elif account_age_days > 365:   # 1+ year
            return 0.4
        elif account_age_days > 90:    # 3+ months
            return 0.3
        elif account_age_days > 30:    # 1+ month
            return 0.2
        elif account_age_days > 0:
            return 0.1
        return 0.0

    def _calculate_activity_uniqueness(self, metrics) -> float:
        uniqueness_score = 0.0
        
        total_interactions = metrics.likes_given_count + metrics.comments_count
        
        if metrics.posts_count > 500:
            uniqueness_score += 0.4
        elif metrics.posts_count > 100:
            uniqueness_score += 0.3
        elif metrics.posts_count > 20:
            uniqueness_score += 0.2
        elif metrics.posts_count > 5:
            uniqueness_score += 0.1
        elif metrics.posts_count > 0:
            uniqueness_score += 0.05

        if total_interactions > 5000:
            uniqueness_score += 0.3
        elif total_interactions > 1000:
            uniqueness_score += 0.2
        elif total_interactions > 100:
            uniqueness_score += 0.15
        elif total_interactions > 10:
            uniqueness_score += 0.1
        elif total_interactions > 0:
            uniqueness_score += 0.05

        if metrics.account_age_days > 0:
            activity_ratio = (metrics.posts_count + total_interactions) / metrics.account_age_days
            if activity_ratio > 0.5:
                uniqueness_score += 0.3
            elif activity_ratio > 0.1:
                uniqueness_score += 0.2
            elif activity_ratio > 0.01:
                uniqueness_score += 0.1

        return min(uniqueness_score, 1.0)

    def _calculate_social_network_uniqueness(self, metrics) -> float:
        network_score = 0.0
        total_connections = metrics.following_count + metrics.follower_count
        
        if total_connections > 10000:
            network_score += 0.4
        elif total_connections > 1000:
            network_score += 0.3
        elif total_connections > 100:
            network_score += 0.2
        elif total_connections > 20:
            network_score += 0.15
        elif total_connections > 5:
            network_score += 0.1
        elif total_connections > 0:
            network_score += 0.05

        if metrics.follower_count > 0 and metrics.following_count > 0:
            follow_ratio = metrics.follower_count / metrics.following_count
            if 0.1 <= follow_ratio <= 10:  # Balanced following/follower ratio
                network_score += 0.3
            elif 0.05 <= follow_ratio <= 20:
                network_score += 0.2
            else:
                network_score += 0.1

        if metrics.follower_count > metrics.posts_count and metrics.posts_count > 0:
            engagement_potential = metrics.follower_count / metrics.posts_count
            if engagement_potential > 10:
                network_score += 0.3
            elif engagement_potential > 5:
                network_score += 0.2
            elif engagement_potential > 1:
                network_score += 0.1

        return min(network_score, 1.0)

    def _calculate_content_uniqueness(self, activities) -> float:
        content_score = 0.0
        
        activity_types = 0
        if len(activities.posts_created) > 0:
            activity_types += 1
        if len(activities.likes_given) > 0:
            activity_types += 1
        if len(activities.comments_made) > 0:
            activity_types += 1
        if len(activities.following_list) > 0:
            activity_types += 1

        content_score += (activity_types / 4.0) * 0.4

        if activities.posts_created:
            unique_sources = set(post.source_app for post in activities.posts_created)
            content_score += min(len(unique_sources) / 3.0, 1.0) * 0.3

            posts_with_content = sum(1 for post in activities.posts_created 
                                   if post.title and len(post.title.strip()) > 0)
            if posts_with_content > 0:
                content_score += min(posts_with_content / len(activities.posts_created), 1.0) * 0.3

        return min(content_score, 1.0)

    def calculate_ownership_score(self) -> float:
        return 1.0 if settings.OWNER_ADDRESS else 0.0

    def calculate_final_score(self, quality: float, authenticity: float, uniqueness: float, ownership: float) -> float:
        return (
            quality * 0.30
            + authenticity * 0.35
            + uniqueness * 0.25
            + ownership * 0.10
        )

    def build_attributes(self, instagram_data: InstagramContribution, ai_result: Optional[Dict] = None) -> Dict[str, Any]:
        attributes = {
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
            "phone_confirmed": instagram_data.data.profile.phone_confirmed,
            "private_account": instagram_data.data.profile.private_account,
        }
        
        if ai_result:
            attributes.update({
                "ai_detection": {
                    "is_ai_generated": ai_result.get('is_ai_generated', False),
                    "confidence": ai_result.get('confidence', 0.0),
                    "indicators": ai_result.get('indicators', []),
                    "authenticity_impact": max(0.0, 1.0 - ai_result.get('confidence', 0.0))
                }
            })

        return attributes
