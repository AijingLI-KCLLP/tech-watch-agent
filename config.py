import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR = DATA_DIR / 'uploads'
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

SQLITE_PATH = DATA_DIR / 'tech_watch.db'
CHROMA_PATH = DATA_DIR / 'chroma'
CHROMA_COLLECTION = "tech_watch"

LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "openai/gpt-oss-20b")
LMSTUDIO_EMBEDDING_MODEL = os.getenv("LMSTUDIO_EMBEDDING_MODEL", "text-embedding-nomic-embed-text-v1.5")
LMSTUDIO_API_KEY = "lm-studio"

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Chunking
CHUNK_SIZE = 800  # 字符
CHUNK_OVERLAP = 100

# num of chunk for each retrieval
TOP_K = 5
# Minimum cosine similarity for a chunk to be considered usable answer context.
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.45"))

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_PODCAST_AUDIO_BYTES = int(os.getenv("MAX_PODCAST_AUDIO_BYTES", str(750 * 1024 * 1024)))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# "vision" is reserved for a future multimodal-model extractor.
IMAGE_EXTRACTION_MODE = os.getenv("IMAGE_EXTRACTION_MODE", "ocr").strip().lower()
