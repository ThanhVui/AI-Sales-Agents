from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseAIAdvisor(ABC):
    """
    Abstract Base Class for AI Sales Advisors.
    Enables pluggable domain-specific AI logic (Real Estate, Insurance, Retail, etc.)
    without modifying core automation or database systems.
    """
    
    @abstractmethod
    def generate_outreach_message(self, customer: Dict[str, Any], template: Optional[str] = None) -> str:
        """
        Generate or personalize an outreach message for a specific customer.
        """
        pass

    @abstractmethod
    def consult_response(self, customer: Dict[str, Any], user_reply: str, conversation_history: list = None) -> str:
        """
        Generate an intelligent consultation response when the customer replies.
        """
        pass

