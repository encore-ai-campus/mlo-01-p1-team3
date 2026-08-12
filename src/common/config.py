"""원본 세 실행 파일에서 공통으로 사용하던 환경 설정."""

# =============================================================================
# [공통 설정 시작] .env 로드 및 API·DB 연결 설정
# 기능: 원본 파일의 환경변수, BASE_URL, MySQL/MongoDB 설정을 한 곳에서 공유한다.
# =============================================================================
import os

import pymysql
from dotenv import load_dotenv


load_dotenv()

BASE_URL = "http://192.168.0.51:4000"
PUBLIC_KEY_URL = f"{BASE_URL}/api/v1/public-key"
CARS_URL = f"{BASE_URL}/api/v1/cars"
CHANGES_URL = f"{BASE_URL}/api/v1/changes"
FAQ_URL = f"{BASE_URL}/faqs"

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "car_data")
MONGO_COLLECTION = os.getenv("MONGO_COLLECTION", "faqs")
# =============================================================================
# [공통 설정 끝]
# =============================================================================
