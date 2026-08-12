from collection.faq import collect_faqs
from loading.mongo import connect,upsert
def run_once():
 client,col=connect();counts={"fetched":0,"inserted":0,"updated":0,"unchanged":0,"failed":0}
 try:
  rows=collect_faqs();counts["fetched"]=len(rows)
  for row in rows:
   try:counts[upsert(col,row)]+=1
   except Exception:counts["failed"]+=1
  return counts
 finally:client.close()
