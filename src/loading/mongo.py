from datetime import datetime,timezone
from pymongo import ASCENDING,MongoClient
from common.config import MONGO_URI,MONGO_DATABASE,MONGO_COLLECTION
FIELDS=("faq_id","brand","brand_code","category","question","answer","source_url","reviewed_at","crawl_url")
def connect():
 client=MongoClient(MONGO_URI,serverSelectionTimeoutMS=5000);client.admin.command("ping");col=client[MONGO_DATABASE][MONGO_COLLECTION];col.create_index([("faq_id",ASCENDING)],unique=True,name="uq_faq_id");col.create_index([("brand",ASCENDING)]);col.create_index([("category",ASCENDING)]);return client,col
def upsert(col,row):
 old=col.find_one({"faq_id":row["faq_id"]},{k:1 for k in FIELDS})
 if old and all(old.get(k)==row.get(k) for k in FIELDS):return "unchanged"
 now=datetime.now(timezone.utc)
 if old:col.update_one({"_id":old["_id"]},{"$set":{**row,"updated_at":now}});return "updated"
 result=col.update_one({"faq_id":row["faq_id"]},{"$set":{**row,"updated_at":now},"$setOnInsert":{"created_at":now}},upsert=True);return "inserted" if result.upserted_id else "unchanged"
