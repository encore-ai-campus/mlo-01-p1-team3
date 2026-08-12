import time
from pipelines.faq import run_once
if __name__=="__main__":
 while True: print(run_once());time.sleep(300)
