import os
from dotenv import load_dotenv
import pymysql
load_dotenv()
BASE_URL=os.getenv("BASE_URL","http://192.168.0.51:4000")
MYSQL_CONFIG={"host":os.getenv("MYSQL_HOST"),"port":int(os.getenv("MYSQL_PORT",3306)),"user":os.getenv("MYSQL_USER"),"password":os.getenv("MYSQL_PASSWORD"),"database":os.getenv("MYSQL_DATABASE"),"charset":"utf8mb4","cursorclass":pymysql.cursors.DictCursor,"autocommit":False}
MONGO_URI=os.getenv("MONGO_URI","mongodb://localhost:27017"); MONGO_DATABASE=os.getenv("MONGO_DATABASE","car_data"); MONGO_COLLECTION=os.getenv("MONGO_COLLECTION","faqs")
