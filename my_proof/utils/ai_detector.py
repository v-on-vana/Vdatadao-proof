import re
import json
import hashlib
from typing import Dict, List, Tuple
from datetime import datetime, timedelta

class AIDetector:
    """AI-generated content detection utilities for Instagram data validation"""
    
    def __init__(self):
        self.generic_patterns = {
            'domains': ['example.com', 'test.com', 'demo.com', 'sample.com', 'fake.com'],
            'names': ['test', 'user', 'admin', 'demo', 'sample', 'example', 'john doe', 'jane doe'],
            'emails': ['test@', 'user@', 'demo@', 'sample@', 'example@'],
            'usernames': ['test', 'user', 'admin', 'demo', 'sample', 'example', 'johndoe']
        }
    
    def detect_ai_content(self, data: Dict) -> Dict:
        """Comprehensive AI content detection for Instagram data"""
        indicators = []
        confidence = 0.0
        
        timestamp_score = self._analyze_timestamp_patterns(data)
        if timestamp_score > 0.7:
            indicators.append('SUSPICIOUS_TIMESTAMP')
            confidence += 0.20
        
        realism_score = self._check_data_realism(data)
        if realism_score < 0.5:
            indicators.append('UNREALISTIC_DATA')
            confidence += 0.25
        
        pattern_score = self._analyze_patterns(data)
        if pattern_score > 0.6:
            indicators.append('REGULAR_PATTERNS')
            confidence += 0.15
        
        diversity_score = self._analyze_content_diversity(data)
        if diversity_score < 0.4:
            indicators.append('LOW_DIVERSITY')
            confidence += 0.10
        
        consistency_score = self._check_consistency(data)
        if consistency_score < 0.6:
            indicators.append('INCONSISTENT_DATA')
            confidence += 0.10
        
        behavioral_score = self._analyze_behavioral_patterns(data)
        if behavioral_score > 0.7:
            indicators.append('ARTIFICIAL_BEHAVIOR')
            confidence += 0.15
        
        language_score = self._analyze_language_patterns(data)
        if language_score > 0.6:
            indicators.append('ARTIFICIAL_LANGUAGE')
            confidence += 0.05
        
        return {
            'is_ai_generated': confidence > 0.5,
            'confidence': min(confidence, 1.0),
            'indicators': indicators,
            'scores': {
                'timestamp': timestamp_score,
                'realism': realism_score,
                'patterns': pattern_score,
                'diversity': diversity_score,
                'consistency': consistency_score,
                'behavioral': behavioral_score,
                'language': language_score
            },
            'authenticity_impact': max(0.0, 1.0 - confidence)
        }
    
    def _analyze_timestamp_patterns(self, data: Dict) -> float:
        """Analyze timestamp for suspicious patterns in Instagram data"""
        score = 0.0
        
        processing_timestamp = data.get('metadata', {}).get('processing_timestamp', 0)
        current_time = int(datetime.now().timestamp() * 1000)
        
        if processing_timestamp > current_time:
            score += 0.4
        
        if processing_timestamp % 1000000 == 0:
            score += 0.3
        
        activities = data.get('data', {}).get('activities', {})
        
        posts = activities.get('posts_created', [])
        if posts:
            timestamps = [post.get('creation_timestamp', 0) for post in posts]
            if self._has_regular_intervals(timestamps):
                score += 0.2
            
            if any(ts % 1000 == 0 for ts in timestamps):
                score += 0.1
        
        return min(score, 1.0)
    
    def _check_data_realism(self, data: Dict) -> float:
        """Check if Instagram data content is realistic"""
        score = 1.0
        
        contributor = data.get('contributor', {})
        profile = data.get('data', {}).get('profile', {})
        metrics = data.get('data', {}).get('metrics', {})
        
        email = contributor.get('email', '')
        if not self._is_realistic_email(email):
            score -= 0.2
        
        name = contributor.get('name', '')
        if not self._is_realistic_name(name):
            score -= 0.2
        

        username = profile.get('username', '')
        if not self._is_realistic_username(username):
            score -= 0.2
        

        score -= self._check_metrics_realism(metrics) * 0.3
        

        if profile.get('email', '') != contributor.get('email', ''):
            if profile.get('email', '') and contributor.get('email', ''):
                score -= 0.1
        
        return max(0.0, score)
    
    def _analyze_patterns(self, data: Dict) -> float:
        """Analyze data for regular patterns"""
        score = 0.0
        
        metrics = data.get('data', {}).get('metrics', {})
        

        round_metrics = 0
        total_metrics = 0
        
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                total_metrics += 1
                if value % 10 == 0 or value % 100 == 0:
                    round_metrics += 1
        
        if total_metrics > 0:
            round_ratio = round_metrics / total_metrics
            if round_ratio > 0.5:
                score += 0.3
        

        contribution_id = data.get('contribution_id', '')
        if re.match(r'^meta_export_\d{10,13}$', contribution_id):
            timestamp_part = contribution_id.replace('meta_export_', '')
            if timestamp_part.endswith('000'):
                score += 0.2
        

        username = data.get('data', {}).get('profile', {}).get('username', '').lower()
        if any(pattern in username for pattern in self.generic_patterns['usernames']):
            score += 0.3
        

        wallet = data.get('contributor', {}).get('wallet_address', '')
        if re.match(r'^0x[a-f0-9]{40}$', wallet.lower()) and '000' in wallet:
            score += 0.2
        
        return min(score, 1.0)
    
    def _analyze_content_diversity(self, data: Dict) -> float:
        """Analyze content diversity in Instagram data"""

        analysis_data = {k: v for k, v in data.items() if k != 'raw_export_data'}
        if 'data' in analysis_data and 'raw_export_data' in analysis_data['data']:
            analysis_data['data'] = {k: v for k, v in analysis_data['data'].items() if k != 'raw_export_data'}
        
        data_str = json.dumps(analysis_data, sort_keys=True)
        

        unique_chars = len(set(data_str))
        total_chars = len(data_str)
        
        if total_chars == 0:
            return 0.0
        
        char_diversity = unique_chars / total_chars
        

        words = re.findall(r'\b\w+\b', data_str.lower())
        if len(words) == 0:
            return char_diversity
        
        unique_words = len(set(words))
        word_diversity = unique_words / len(words)
        

        activities = data.get('data', {}).get('activities', {})
        activity_diversity = self._calculate_activity_diversity(activities)
        
        return (char_diversity + word_diversity + activity_diversity) / 3
    
    def _check_consistency(self, data: Dict) -> float:
        """Check data consistency for Instagram data"""
        score = 1.0
        

        processing_timestamp = data.get('metadata', {}).get('processing_timestamp', 0)
        collection_date = data.get('metadata', {}).get('collection_date')
        
        if collection_date and processing_timestamp:
            try:
                collection_timestamp = int(datetime.fromisoformat(
                    collection_date.replace('Z', '+00:00')
                ).timestamp() * 1000)
                
                if abs(collection_timestamp - processing_timestamp) > 3600000:  # 1 hour tolerance
                    score -= 0.3
            except:
                score -= 0.2
        

        metrics = data.get('data', {}).get('metrics', {})
        total_interactions = metrics.get('total_interactions', 0)
        calculated_interactions = metrics.get('likes_given_count', 0) + metrics.get('comments_count', 0)
        
        if total_interactions != calculated_interactions and both_exist(total_interactions, calculated_interactions):
            score -= 0.2
        

        required_paths = [
            'contribution_id',
            'contributor.wallet_address',
            'contributor.email',
            'data.platform',
            'data.profile.username'
        ]
        
        for path in required_paths:
            if not self._get_nested_value(data, path):
                score -= 0.1
        
        return max(0.0, score)
    
    def _has_regular_intervals(self, timestamps: List[int]) -> bool:
        """Check if timestamps have regular intervals"""
        if len(timestamps) < 3:
            return False
        
        sorted_timestamps = sorted(timestamps)
        intervals = []
        
        for i in range(1, len(sorted_timestamps)):
            intervals.append(sorted_timestamps[i] - sorted_timestamps[i-1])
        

        if len(set(intervals)) == 1:
            return True
        

        common_intervals = [3600, 86400, 604800]
        for interval in intervals:
            if any(interval % common == 0 for common in common_intervals):
                return True
        
        return False
    
    def _is_realistic_email(self, email: str) -> bool:
        """Check if email is realistic"""
        if not email or '@' not in email:
            return False
        
        domain = email.split('@')[-1].lower()
        
        if domain in self.generic_patterns['domains']:
            return False
        
        if any(pattern in email.lower() for pattern in self.generic_patterns['emails']):
            return False
        
        if len(email) < 5 or len(email) > 100:
            return False
        
        if re.match(r'^[a-z]+\d*@[a-z]+\.com$', email.lower()):
            return False
        
        return True
    
    def _is_realistic_name(self, name: str) -> bool:
        """Check if name is realistic"""
        if not name or len(name) < 2 or len(name) > 50:
            return False
        
        if name.lower() in self.generic_patterns['names']:
            return False
        
        if re.match(r'^[a-z]+\s[a-z]+$', name.lower()) and len(name.split()) == 2:
            return False
        
        return True
    
    def _is_realistic_username(self, username: str) -> bool:
        """Check if Instagram username is realistic"""
        if not username or len(username) < 3 or len(username) > 30:
            return False
        
        if username.lower() in self.generic_patterns['usernames']:
            return False
        
        if re.match(r'^[a-z]+\d*$', username.lower()) and len(username) < 8:
            return False
        
        return True
    
    def _check_metrics_realism(self, metrics: Dict) -> float:
        """Check if metrics are realistic (returns penalty score 0-1)"""
        penalty = 0.0
        
        posts_count = metrics.get('posts_count', 0)
        followers = metrics.get('follower_count', 0)
        following = metrics.get('following_count', 0)
        likes_given = metrics.get('likes_given_count', 0)
        account_age_days = metrics.get('account_age_days', 0)
        

        if account_age_days > 0:
            posts_per_day = posts_count / account_age_days
            if posts_per_day > 10:
                penalty += 0.3
        

        if following > 0 and followers / following > 100:
            penalty += 0.2
        

        if account_age_days > 0 and likes_given > 0:
            likes_per_day = likes_given / account_age_days
            if likes_per_day > 1000:
                penalty += 0.3
        

        if followers == 0 and posts_count > 50:
            penalty += 0.2
        
        return min(penalty, 1.0)
    
    def _calculate_activity_diversity(self, activities: Dict) -> float:
        """Calculate diversity in activities"""
        if not activities:
            return 0.0
        
        activity_counts = {}
        
        for activity_type, activity_list in activities.items():
            if isinstance(activity_list, list):
                activity_counts[activity_type] = len(activity_list)
        
        if not activity_counts:
            return 0.0
        
        total_activities = sum(activity_counts.values())
        if total_activities == 0:
            return 0.0
        

        diversity = 0.0
        for count in activity_counts.values():
            if count > 0:
                ratio = count / total_activities
                diversity -= ratio * (ratio if ratio > 0 else 0)
        

        max_diversity = len(activity_counts)
        if max_diversity > 1:
            diversity = diversity / max_diversity
        
        return min(diversity, 1.0)
    
    def _get_nested_value(self, data: Dict, path: str):
        """Get nested value from data using dot notation"""
        keys = path.split('.')
        current = data
        
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
        
        return current

    def _analyze_behavioral_patterns(self, data: Dict) -> float:
        """Analyze behavioral patterns for AI detection"""
        score = 0.0
        
        activities = data.get('data', {}).get('activities', {})
        metrics = data.get('data', {}).get('metrics', {})
        
        posts_count = metrics.get('posts_count', 0)
        followers = metrics.get('follower_count', 0)
        following = metrics.get('following_count', 0)
        account_age_days = metrics.get('account_age_days', 1)
        
        if followers == 0 and following > 100:
            score += 0.3
        
        if posts_count == 0 and following > 0:
            score += 0.2
        
        following_list = activities.get('following_list', [])
        if len(following_list) > 0:
            usernames = [f.get('username', '') for f in following_list if f.get('username')]
            if len(usernames) > 3:
                sequential_count = 0
                for i in range(1, len(usernames)):
                    if usernames[i].startswith(usernames[i-1][:3]):
                        sequential_count += 1
                
                if sequential_count / len(usernames) > 0.5:
                    score += 0.2
        
        posts = activities.get('posts_created', [])
        if len(posts) > 2:
            creation_times = [p.get('creation_timestamp', 0) for p in posts]
            creation_times.sort()
            
            intervals = []
            for i in range(1, len(creation_times)):
                if creation_times[i] > 0 and creation_times[i-1] > 0:
                    intervals.append(creation_times[i] - creation_times[i-1])
            
            if len(intervals) > 0:
                avg_interval = sum(intervals) / len(intervals)
                if avg_interval < 3600:  # Posts less than 1 hour apart
                    score += 0.15
        
        if account_age_days > 0:
            activity_rate = (posts_count + len(following_list)) / account_age_days
            if activity_rate > 50:  # Too much activity per day
                score += 0.25
        
        return min(score, 1.0)
    
    def _analyze_language_patterns(self, data: Dict) -> float:
        """Analyze language patterns for AI detection"""
        score = 0.0
        
        profile = data.get('data', {}).get('profile', {})
        contributor = data.get('contributor', {})
        
        username = profile.get('username', '').lower()
        display_name = profile.get('display_name', '').lower()
        contributor_name = contributor.get('name', '').lower()
        
        if username and display_name:
            if username == display_name.replace(' ', ''):
                score += 0.1
        
        if re.match(r'^[a-z]+\d{4,}$', username):
            score += 0.2
        
        generic_words = ['user', 'test', 'admin', 'demo', 'sample', 'account', 'profile']
        if any(word in username for word in generic_words):
            score += 0.3
        
        if contributor_name:
            words = contributor_name.split()
            if len(words) == 2 and all(len(word) < 5 for word in words):
                score += 0.2
        
        bio = profile.get('bio', '')
        if bio:
            if len(bio.split()) < 3 or bio.count(' ') == 0:
                score += 0.1
            
            if any(generic in bio.lower() for generic in ['lorem', 'ipsum', 'test', 'demo']):
                score += 0.3
        
        return min(score, 1.0)

def both_exist(val1, val2) -> bool:
    """Check if both values exist and are not zero"""
    return val1 is not None and val2 is not None and val1 != 0 and val2 != 0