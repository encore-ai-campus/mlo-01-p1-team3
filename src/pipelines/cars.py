from datetime import datetime
import pymysql
from common.config import MYSQL_CONFIG
from collection.cars import get_api_key,request_api,CARS_URL,CHANGES_URL
from preprocessing.cars import normalize_car
from loading.mysql import create_tables,upsert_business_area,upsert_car,write_log,last_seq
def initial():
 return _run(False)
def incremental():
 return _run(True)
def _run(changes):
 started=datetime.now();stats=[0,0,0,0];conn=pymysql.connect(**MYSQL_CONFIG);c=conn.cursor();create_tables(conn);seq=last_seq(c) if changes else None
 try:
  key=get_api_key();page=1
  while page<=100:
   url=f"{CHANGES_URL}?after_seq={seq}&limit=100" if changes else f"{CARS_URL}?sort=newest&page={page}&page_size=100"
   body,key=request_api(url,key);rows=body.get("data",[])
   if not rows:break
   for event in rows:
    raw=event.get("payload") if changes else event
    if not raw:stats[3]+=1;continue
    upsert_business_area(c,raw);result=upsert_car(c,normalize_car(raw));stats[0]+=1;stats[1 if result=="inserted" else 2]+=1
    if changes:seq=event.get("seq",seq)
   conn.commit();page+=1
   if changes and not body.get("meta",{}).get("has_more",False):break
  write_log(conn,"AutoData Lab Changes" if changes else "AutoData Lab Cars Initial",started,datetime.now(),stats,"SUCCESS" if not stats[3] else "PARTIAL_SUCCESS",seq);return {"fetched":stats[0],"inserted":stats[1],"updated":stats[2],"failed":stats[3],"last_seq":seq}
 finally:c.close();conn.close()
