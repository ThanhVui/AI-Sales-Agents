import os
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
from src.ai.base import BaseAIAdvisor
from src.config import settings

class RealEstateAdvisor(BaseAIAdvisor):
    """
    Real Estate AI Advisor specialized in Property Sales & Rentals (e.g., Masteri Centre Point).
    """

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.client = None
        if self.api_key:
            try:
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(timeout=settings.GEMINI_TIMEOUT_SECONDS)
                )
            except Exception as e:
                print(f"[RealEstateAdvisor] Warning: Failed to initialize Gemini Client: {e}")

    def generate_outreach_message(self, customer: Dict[str, Any], template: Optional[str] = None) -> str:
        """
        Populates outreach template with customer parameters.
        Supported tokens:
        - [Tên Khách Hàng]
        - [Tên Căn Hộ]
        - [Mã Tòa]
        - [Trục Căn]
        - [Giá Gốc]
        - [Điện Thoại]
        """
        name = customer.get("name") or customer.get("customer_name") or "Quý Khách"
        apt = customer.get("apartment") or customer.get("apartment_name") or "căn hộ"
        block = customer.get("block") or customer.get("building_code") or ""
        axis = customer.get("axis") or ""
        price = customer.get("price") or ""
        phone = customer.get("phone") or ""

        if not template:
            template = (
                "Anh/Chị [Tên Khách Hàng] ơi! Em đang có khách hàng muốn mua hoặc THUÊ căn [Tên Căn Hộ].\n\n"
                "Mình có thể BÁN hoặc CHO THUÊ không ạ?\n"
                "Nếu có, hãy cho em biết giá bán nhé!\n"
                "Em xin cảm ơn và chúc Anh/Chị có một ngày thật tuyệt vời!"
            )

        msg = template
        msg = msg.replace("[Tên Khách Hàng]", str(name))
        msg = msg.replace("[Tên Căn Hộ]", str(apt))
        msg = msg.replace("[Mã Tòa]", str(block))
        msg = msg.replace("[Trục Căn]", str(axis))
        msg = msg.replace("[Giá Gốc]", str(price))
        msg = msg.replace("[Điện Thoại]", str(phone))

        return msg.strip()

    def consult_response(self, customer: Dict[str, Any], user_reply: str, conversation_history: list = None) -> str:
        """
        Generates an AI consultation reply based on customer context and their response.
        """
        if not self.client:
            return "Dạ em đã nhận được thông tin, em sẽ liên hệ lại với Anh/Chị ngay ạ!"

        name = customer.get("name") or "Khách hàng"
        apt = customer.get("apartment") or "căn hộ"
        price = customer.get("price") or "theo thị trường"

        prompt = f"""Bạn là Trợ lý AI Bất Động Sản chuyên nghiệp, lịch sự, nhiệt tình của dự án Masteri Centre Point.
Thông tin khách hàng:
- Tên: {name}
- Căn hộ: {apt}
- Giá gốc/tham khảo: {price}

Khách hàng vừa trả lời: "{user_reply}"

Nhiệm vụ của bạn:
- Viết câu trả lời ngắn gọn, thân thiện (tối đa 2-3 câu), xưng "Em" gọi "Anh/Chị" hoặc "Anh {name}".
- Nếu khách đồng ý bán/cho thuê, hỏi thêm về mức giá mong muốn hoặc lịch hẹn trao đổi.
- Nếu khách không bán/thuê, gửi lời cảm ơn và chúc một ngày tốt lành.
"""
        models_to_try = [settings.GEMINI_MODEL, "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
        for model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"[RealEstateAdvisor] Model {model} error: {e}, trying next...")
                continue

        return "Dạ em cảm ơn Anh/Chị nhiều ạ. Em sẽ kiểm tra và phản hồi lại sớm nhất cho Anh/Chị nhé!"

