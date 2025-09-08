from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from my_proof.models.proof_response import ProofResponse

class BaseProcessor(ABC):
    
    @abstractmethod
    def process_data(self, input_data: Dict[str, Any], schema_matches: bool, google_user: Optional[Any], errors: List[str]) -> None:
        pass
    
    @abstractmethod
    def verify_profile_match(self, google_user: Any, input_data: Dict[str, Any]) -> bool:
        pass
