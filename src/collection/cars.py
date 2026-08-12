import time, requests
from common.config import BASE_URL
PUBLIC_KEY_URL=f"{BASE_URL}/api/v1/public-key"; CARS_URL=f"{BASE_URL}/api/v1/cars"; CHANGES_URL=f"{BASE_URL}/api/v1/changes"
def get_api_key():
 r=requests.get(PUBLIC_KEY_URL,timeout=10); r.raise_for_status(); return r.json()["data"]["current"]["api_key"]
def request_api(url,key):
 retries=0
 while True:
  try:
   r=requests.get(url,headers={"X-API-Key":key},timeout=(10,30))
   if r.status_code==403:
    retries+=1
    if retries>10:r.raise_for_status()
    key=get_api_key();time.sleep(2);continue
   if r.status_code==429:
    retries+=1
    if retries>10:r.raise_for_status()
    try: wait=int(r.headers.get("Retry-After",""))
    except ValueError: wait=min(5*retries,60)
    time.sleep(wait);continue
   r.raise_for_status();return r.json(),key
  except (requests.exceptions.ConnectTimeout,requests.exceptions.ReadTimeout,requests.exceptions.ConnectionError):
   retries+=1
   if retries>10:raise
   time.sleep(min(5*retries,60))
