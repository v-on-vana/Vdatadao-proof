from typing import Dict, Any, Optional

from my_proof.scorers.base_scorer import BaseScorer
from my_proof.config import settings

class GoogleScorer(BaseScorer):
    
    def calculate_quality_score(self, input_data: Dict[str, Any]) -> float:
        return 1.0
    
    def calculate_authenticity_score(self, input_data: Dict[str, Any], google_user: Optional[Any] = None) -> float:
        return 1.0 if google_user else 0.0
    
    def calculate_uniqueness_score(self, input_data: Dict[str, Any]) -> float:
        return 1.0
    
    def calculate_ownership_score(self) -> float:
        return 1.0 if settings.OWNER_ADDRESS else 0.0
    
    def calculate_final_score(self, quality: float, authenticity: float, uniqueness: float, ownership: float) -> float:
        return (
            quality * 0.4
            + authenticity * 0.3
            + uniqueness * 0.2
            + ownership * 0.1
        )
    
    def build_attributes(self, input_data: Dict[str, Any], google_user: Optional[Any] = None, ai_result: Optional[Dict] = None) -> Dict[str, Any]:
        return {
            "schema_type": "google-profile.json",
            "user_email": input_data.get("email"),
            "user_id": input_data.get("userId"),
            "profile_name": input_data.get("profile", {}).get("name"),
            "verified_with_oauth": google_user is not None,
        }
