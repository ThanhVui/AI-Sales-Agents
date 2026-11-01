from typing import Dict, Any, Optional
from src.ai.base import BaseAIAdvisor

class GenericSalesAdvisor(BaseAIAdvisor):
    """
    Generic AI Sales Advisor for general businesses (Retail, Services, Consulting, Insurance).
    Can be customized or replaced easily without affecting the automation core.
    """

    def generate_outreach_message(self, customer: Dict[str, Any], template: Optional[str] = None) -> str:
        name = customer.get("name") or "Quý Khách"
        phone = customer.get("phone") or ""

        if not template:
            template = "Xin chào [Tên Khách Hàng], em là chuyên viên tư vấn. Em xin phép được hỗ trợ thông tin tới Anh/Chị ạ!"

        msg = template.replace("[Tên Khách Hàng]", str(name))
        msg = msg.replace("[Điện Thoại]", str(phone))
        return msg.strip()

    def consult_response(self, customer: Dict[str, Any], user_reply: str, conversation_history: list = None) -> str:
        name = customer.get("name") or "Quý Khách"
        return f"Dạ em cảm ơn {name} đã phản hồi. Em sẽ liên hệ hỗ trợ mình ngay ạ!"

