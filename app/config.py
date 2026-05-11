from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    GLOSSARY_DIR: str = os.getenv("GLOSSARY_DIR", "/tmp/glossaries")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/tmp/uploads")

settings = Settings()
