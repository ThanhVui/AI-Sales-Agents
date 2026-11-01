"""
Synexan AI Sales - Zalo Real Estate Automation
Main Application Entry Point
"""
import uvicorn
from src.config import settings
from src.web.app import app

if __name__ == "__main__":
    print(f"==================================================")
    print(f"🚀 Synexan AI Sales Server starting...")
    print(f"📍 Host: {settings.HOST}:{settings.PORT}")
    print(f"🌐 Dashboard URL: http://localhost:{settings.PORT}")
    print(f"🤖 AI Domain: Real Estate (Pluggable via src/ai/)")
    print(f"⚡ Headless Mode: {settings.HEADLESS}")
    print(f"==================================================")
    uvicorn.run(
        "src.web.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False
    )
