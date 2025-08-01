from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class Contributor(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    email: str = Field(..., format="email")
    name: str
    locale: str

class InstagramProfile(BaseModel):
    username: str
    display_name: str
    email: str = Field(..., format="email")
    account_type: str
    date_of_birth: Optional[str] = None
    phone_confirmed: bool = False
    private_account: bool = False

class InstagramMetrics(BaseModel):
    posts_count: int = Field(..., ge=0)
    following_count: int = Field(..., ge=0)
    follower_count: int = Field(..., ge=0)
    likes_given_count: int = Field(..., ge=0)
    comments_count: int = Field(..., ge=0)
    account_age_days: int = Field(..., ge=0)
    total_interactions: int = Field(..., ge=0)
    has_story_activity: bool = False

class FollowingItem(BaseModel):
    username: str
    followed_at: int

class LikeItem(BaseModel):
    target_username: str
    count: int = Field(..., ge=0)
    last_activity: int

class PostItem(BaseModel):
    creation_timestamp: int
    title: Optional[str] = None
    source_app: str
    has_photo: bool = False
    has_camera_metadata: bool = False

class CommentItem(BaseModel):
    timestamp: int
    target_username: str

class InstagramActivities(BaseModel):
    following_list: List[FollowingItem] = []
    likes_given: List[LikeItem] = []
    posts_created: List[PostItem] = []
    comments_made: List[CommentItem] = []

class InstagramSecurity(BaseModel):
    last_login: int
    contact_syncing: bool = False
    has_shared_live_video: bool = False

class FolderStructure(BaseModel):
    metaFolderId: str
    instagramFolderId: str
    instagramFolderName: str

class PrivacySettings(BaseModel):
    contains_pii: bool = True
    anonymization_level: str = "partial"
    retention_policy: str = "user_controlled"

class InstagramData(BaseModel):
    platform: str = Field(default="instagram", pattern="^instagram$")
    source_type: str = "meta_export"
    extraction_method: str = "google_drive_api"
    profile: InstagramProfile
    metrics: InstagramMetrics
    activities: InstagramActivities
    security: InstagramSecurity
    raw_export_data: Optional[Dict[str, Any]] = None

class InstagramMetadata(BaseModel):
    version: str = Field(default="1.0.0")
    schema_version: str = Field(default="vana_datadao_v1")
    source: str = "Google Drive - Meta Data Export"
    collection_date: str = Field(..., description="ISO 8601 datetime string")
    data_type: str = Field(default="instagram_meta_export")
    processing_timestamp: int
    extraction_completeness: int = Field(..., ge=0, le=100)
    folder_structure: FolderStructure
    privacy_settings: PrivacySettings
    quality_score: int = Field(..., ge=0, le=100)
    data_freshness: int = Field(..., ge=0, le=100)

class InstagramContribution(BaseModel):
    contribution_id: str
    contributor: Contributor
    data: InstagramData
    metadata: InstagramMetadata
    created_at: str = Field(..., description="ISO 8601 datetime string")
    updated_at: str = Field(..., description="ISO 8601 datetime string")