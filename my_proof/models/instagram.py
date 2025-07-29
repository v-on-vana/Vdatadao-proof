from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class InstagramProfile(BaseModel):
    """Instagram profile information"""
    displayName: str = Field(..., max_length=150)
    biography: str = Field(..., max_length=150)
    followerCount: int = Field(..., ge=0)
    followingCount: int = Field(..., ge=0)
    postCount: int = Field(..., ge=0)
    isVerified: Optional[bool] = False
    isPrivate: Optional[bool] = False
    profilePictureUrl: Optional[str] = None
    externalUrl: Optional[str] = None
    category: Optional[str] = None


class InstagramPost(BaseModel):
    """Instagram post data"""
    postId: str
    caption: Optional[str] = Field(None, max_length=2200)
    timestamp: int
    mediaType: str = Field(..., pattern="^(image|video|carousel)$")
    mediaUrls: Optional[List[str]] = []
    hashtags: Optional[List[str]] = []
    mentions: Optional[List[str]] = []
    likeCount: Optional[int] = Field(0, ge=0)
    commentCount: Optional[int] = Field(0, ge=0)
    shareCount: Optional[int] = Field(0, ge=0)
    location: Optional[Dict[str, Any]] = None


class InstagramStory(BaseModel):
    """Instagram story data"""
    storyId: str
    timestamp: int
    mediaType: str = Field(..., pattern="^(image|video)$")
    mediaUrl: Optional[str] = None
    viewCount: Optional[int] = Field(0, ge=0)
    impressions: Optional[int] = Field(0, ge=0)
    stickers: Optional[List[str]] = []


class InstagramReel(BaseModel):
    """Instagram reel data"""
    reelId: str
    caption: Optional[str] = Field(None, max_length=2200)
    timestamp: int
    mediaUrl: Optional[str] = None
    audioInfo: Optional[Dict[str, Any]] = None
    playCount: Optional[int] = Field(0, ge=0)
    likeCount: Optional[int] = Field(0, ge=0)
    commentCount: Optional[int] = Field(0, ge=0)
    shareCount: Optional[int] = Field(0, ge=0)
    effects: Optional[List[str]] = []


class InstagramAnalytics(BaseModel):
    """Instagram analytics and insights"""
    accountInsights: Optional[Dict[str, Any]] = None
    topPosts: Optional[List[Dict[str, Any]]] = []
    audienceInsights: Optional[Dict[str, Any]] = None


class InstagramMetadata(BaseModel):
    """Instagram export metadata"""
    source: str = Field(..., pattern="^(instagram_official_export|instagram_api|third_party_tool)$")
    exportMethod: str
    dataVersion: str
    exportDate: str
    fileCount: int = Field(..., ge=1)
    totalMediaSize: Optional[int] = Field(0, ge=0)
    privacySettings: Optional[Dict[str, Any]] = None


class InstagramData(BaseModel):
    """Complete Instagram data export"""
    userId: str = Field(..., pattern="^[0-9]+$")
    username: str = Field(..., pattern="^[a-zA-Z0-9._]{1,30}$")
    exportTimestamp: int = Field(..., ge=1000000000000)
    profile: InstagramProfile
    posts: Optional[List[InstagramPost]] = []
    stories: Optional[List[InstagramStory]] = []
    reels: Optional[List[InstagramReel]] = []
    analytics: Optional[InstagramAnalytics] = None
    metadata: InstagramMetadata 