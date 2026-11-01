from typing import Dict, Type
from src.ai.base import BaseAIAdvisor
from src.ai.real_estate import RealEstateAdvisor
from src.ai.generic import GenericSalesAdvisor

_REGISTRY: Dict[str, Type[BaseAIAdvisor]] = {
    "real_estate": RealEstateAdvisor,
    "bds": RealEstateAdvisor,
    "generic": GenericSalesAdvisor,
}

def register_advisor(domain: str, advisor_cls: Type[BaseAIAdvisor]):
    """Register a new domain advisor dynamically."""
    _REGISTRY[domain.lower()] = advisor_cls

def get_advisor(domain: str = "real_estate") -> BaseAIAdvisor:
    """
    Factory function to retrieve the domain-specific AI advisor.
    Default: 'real_estate'
    """
    cls = _REGISTRY.get(domain.lower(), RealEstateAdvisor)
    return cls()

