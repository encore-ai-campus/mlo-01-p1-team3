import requests
from bs4 import BeautifulSoup
from common.config import BASE_URL
FAQ_URL=f"{BASE_URL}/faqs"
def collect_faqs():
 r=requests.get(FAQ_URL,timeout=15);r.raise_for_status();out=[]
 for item in BeautifulSoup(r.text,"html.parser").select("article.faq-item"):
  get=lambda s,d=None:(n.get_text(" ",strip=True) if (n:=item.select_one(s)) else d); fid=item.get("data-faq-id");bc=item.get("data-brand");cc=item.get("data-category")
  row={"faq_id":fid,"brand":get('[data-field="brand"]',bc),"brand_code":bc,"category":get('[data-field="category"]',cc),"question":get('[data-field="question"]'),"answer":get('[data-field="answer"]'),"source_url":item.get("data-source-url"),"reviewed_at":item.get("data-reviewed-at"),"crawl_url":FAQ_URL}
  if fid and row["question"] and row["answer"]:out.append(row)
 return out
