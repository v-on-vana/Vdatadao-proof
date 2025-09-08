from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from my_proof.models.proof_response import ProofResponse

class BaseScorer(ABC):
    
    @abstractmethod
    def calculate_quality_score(self, data: Any) -> float:
        pass
    
    @abstractmethod
    def calculate_authenticity_score(self, data: Any, google_user: Optional[Any] = None) -> float:
        pass
    
    @abstractmethod
    def calculate_uniqueness_score(self, data: Any) -> float:
        pass
    
    @abstractmethod
    def calculate_ownership_score(self) -> float:
        pass
    
    @abstractmethod
    def calculate_final_score(self, quality: float, authenticity: float, uniqueness: float, ownership: float) -> float:
        pass
    
    @abstractmethod
    def build_attributes(self, data: Any, google_user: Optional[Any] = None, ai_result: Optional[Dict] = None) -> Dict[str, Any]:
        pass
