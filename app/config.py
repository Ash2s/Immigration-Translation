from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    GLOSSARY_DIR: str = os.getenv("GLOSSARY_DIR", "/tmp/glossaries")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/tmp/uploads")
    JOBS_DIR: str = os.getenv("JOBS_DIR", "/tmp/jobs")

settings = Settings()
