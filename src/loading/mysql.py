"""Original cars/business_areas/crawl_logs MySQL persistence."""
def create_tables(conn):
 with conn.cursor() as c:
  c.execute("CREATE TABLE IF NOT EXISTS business_areas (business_area_code VARCHAR(100) PRIMARY KEY,business_area_name VARCHAR(255),dealer_id VARCHAR(100),dealer_name VARCHAR(100),department VARCHAR(255),position VARCHAR(100)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
  c.execute("CREATE TABLE IF NOT EXISTS cars (car_id BIGINT PRIMARY KEY,listing_number VARCHAR(100) NOT NULL UNIQUE,dealer_id VARCHAR(100),business_area_code VARCHAR(100),brand VARCHAR(100),model VARCHAR(150),trim VARCHAR(150),model_year INT,first_registration_date DATE,mileage_km INT,price BIGINT,currency VARCHAR(20),fuel_type VARCHAR(50),transmission VARCHAR(50),color VARCHAR(50),displacement_cc INT,status VARCHAR(50),accident_count INT,owner_change_count INT,inspection_status VARCHAR(100),province VARCHAR(100),city VARCHAR(100),listing_date DATE,CONSTRAINT fk_car_business_area FOREIGN KEY (business_area_code) REFERENCES business_areas(business_area_code)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
  c.execute("CREATE TABLE IF NOT EXISTS crawl_logs (log_id BIGINT AUTO_INCREMENT PRIMARY KEY,source_type VARCHAR(20),source_name VARCHAR(255),started_at DATETIME,finished_at DATETIME,fetched_count INT DEFAULT 0,inserted_count INT DEFAULT 0,updated_count INT DEFAULT 0,failed_count INT DEFAULT 0,status VARCHAR(30),error_message TEXT,last_seq BIGINT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")
 conn.commit()
def upsert_business_area(c,raw):
 a=raw.get("businessArea")or{};d=raw.get("dealer")or{}
 if a.get("id"): c.execute("INSERT INTO business_areas VALUES(%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE business_area_name=VALUES(business_area_name),dealer_id=VALUES(dealer_id),dealer_name=VALUES(dealer_name),department=VALUES(department),position=VALUES(position)",(a.get("id"),a.get("name"),d.get("code"),d.get("displayName"),d.get("department"),d.get("position")))
def upsert_car(c,car):
 c.execute("SELECT car_id FROM cars WHERE car_id=%s",(car["car_id"],)); exists=c.fetchone()
 keys=("car_id","listing_number","dealer_id","business_area_code","brand","model","trim","model_year","first_registration_date","mileage_km","price","currency","fuel_type","transmission","color","displacement_cc","status","accident_count","owner_change_count","inspection_status","province","city","listing_date")
 columns=','.join(keys); updates=','.join(f"{k}=VALUES({k})" for k in keys[2:]); c.execute(f"INSERT INTO cars ({columns}) VALUES ({','.join(['%s']*len(keys))}) ON DUPLICATE KEY UPDATE {updates}",tuple(car[k] for k in keys)); return "updated" if exists else "inserted"
def write_log(conn,name,started,finished,stats,status,last_seq=None,error=None):
 with conn.cursor() as c:c.execute("INSERT INTO crawl_logs (source_type,source_name,started_at,finished_at,fetched_count,inserted_count,updated_count,failed_count,status,error_message,last_seq) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",("API",name,started,finished,*stats,status,error,last_seq))
 conn.commit()
def last_seq(c):
 c.execute("SELECT last_seq FROM crawl_logs WHERE source_name='AutoData Lab Changes' AND last_seq IS NOT NULL AND status IN ('SUCCESS','PARTIAL_SUCCESS') ORDER BY log_id DESC LIMIT 1"); row=c.fetchone(); return row["last_seq"] if row else 0
