-- MLO MVP logical schema.
-- Target: MySQL-compatible SQL (MySQL 8.x / MariaDB-compatible syntax).
-- Apply with an administrative migration account, then grant only the
-- application tables needed by the Backend writer.

CREATE DATABASE IF NOT EXISTS sales_support_db
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE sales_support_db;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(128) NOT NULL,
    checksum CHAR(64) NOT NULL,
    applied_at DATETIME NOT NULL,
    PRIMARY KEY (version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vehicle_brands (
    brand_id BIGINT NOT NULL,
    name VARCHAR(128) NULL,
    slug VARCHAR(128) NULL,
    country VARCHAR(128) NULL,
    source_updated_at DATETIME NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (brand_id),
    UNIQUE KEY uq_brand_slug (slug),
    KEY ix_brand_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vehicle_models (
    model_id BIGINT NOT NULL,
    brand_id BIGINT NULL,
    name VARCHAR(256) NULL,
    slug VARCHAR(256) NULL,
    body_type VARCHAR(128) NULL,
    source_updated_at DATETIME NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (model_id),
    KEY ix_model_brand (brand_id),
    KEY ix_model_name (name),
    CONSTRAINT fk_model_brand FOREIGN KEY (brand_id) REFERENCES vehicle_brands (brand_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vehicle_locations (
    location_id BIGINT NOT NULL,
    province VARCHAR(128) NULL,
    city VARCHAR(128) NULL,
    sigungu VARCHAR(128) NULL,
    slug VARCHAR(128) NULL,
    source_updated_at DATETIME NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (location_id),
    KEY ix_location_region (province, city, sigungu)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vehicle_dealers (
    dealer_code VARCHAR(128) NOT NULL,
    display_name VARCHAR(128) NULL,
    department VARCHAR(128) NULL,
    position VARCHAR(128) NULL,
    source_updated_at DATETIME NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (dealer_code),
    KEY ix_dealer_department (department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vehicle_business_areas (
    business_area_id VARCHAR(128) NOT NULL,
    name VARCHAR(256) NULL,
    slug VARCHAR(256) NULL,
    parent_business_area_id VARCHAR(128) NULL,
    source_updated_at DATETIME NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (business_area_id),
    KEY ix_business_area_parent (parent_business_area_id),
    CONSTRAINT fk_business_area_parent
        FOREIGN KEY (parent_business_area_id) REFERENCES vehicle_business_areas (business_area_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vehicle_listings (
    listing_id VARCHAR(128) NOT NULL,
    listing_number VARCHAR(128) NULL,
    title VARCHAR(512) NULL,
    description TEXT NULL,
    trim VARCHAR(256) NULL,
    model_id BIGINT NULL,
    location_id BIGINT NULL,
    dealer_code VARCHAR(128) NULL,
    business_area_id VARCHAR(128) NULL,
    model_year SMALLINT NULL,
    first_registration DATE NULL,
    mileage_km BIGINT NULL,
    price_krw DECIMAL(15,0) NULL,
    currency CHAR(3) NULL,
    source_status VARCHAR(64) NULL,
    fuel_type VARCHAR(64) NULL,
    transmission VARCHAR(64) NULL,
    color VARCHAR(64) NULL,
    displacement_cc INT NULL,
    accident_count INT NULL,
    owner_change_count INT NULL,
    inspection_status VARCHAR(128) NULL,
    source_event_id VARCHAR(128) NULL,
    source_sequence BIGINT NULL,
    content_hash CHAR(64) NULL,
    source_url VARCHAR(512) NULL,
    source_created_at DATETIME NULL,
    source_updated_at DATETIME NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (listing_id),
    KEY ix_listing_model (model_id),
    KEY ix_listing_location (location_id),
    KEY ix_listing_dealer (dealer_code),
    KEY ix_listing_business_area (business_area_id),
    KEY ix_listing_source_status (source_status),
    KEY ix_listing_run (run_id),
    KEY ix_listing_source_sequence (source_sequence),
    CONSTRAINT fk_listing_model FOREIGN KEY (model_id) REFERENCES vehicle_models (model_id),
    CONSTRAINT fk_listing_location FOREIGN KEY (location_id) REFERENCES vehicle_locations (location_id),
    CONSTRAINT fk_listing_dealer FOREIGN KEY (dealer_code) REFERENCES vehicle_dealers (dealer_code),
    CONSTRAINT fk_listing_business_area
        FOREIGN KEY (business_area_id) REFERENCES vehicle_business_areas (business_area_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS vehicle_registration_reports (
    report_id BIGINT NOT NULL AUTO_INCREMENT,
    report_month DATE NOT NULL,
    sido_name VARCHAR(128) NOT NULL,
    sigungu_name VARCHAR(128) NOT NULL,
    vehicle_type VARCHAR(128) NOT NULL,
    usage_type VARCHAR(128) NOT NULL,
    quantity BIGINT NULL,
    source_name VARCHAR(128) NOT NULL,
    source_url VARCHAR(512) NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    content_hash CHAR(64) NULL,
    PRIMARY KEY (report_id),
    UNIQUE KEY uq_registration_business
        (report_month, sido_name, sigungu_name, vehicle_type, usage_type),
    KEY ix_registration_month_region (report_month, sido_name, sigungu_name),
    KEY ix_registration_measure (vehicle_type, usage_type),
    KEY ix_registration_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id CHAR(36) NOT NULL,
    pipeline_name VARCHAR(64) NOT NULL,
    schedule_name VARCHAR(64) NULL,
    status VARCHAR(16) NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME NULL,
    collected_count INT NOT NULL DEFAULT 0,
    preprocessed_count INT NOT NULL DEFAULT 0,
    valid_count INT NOT NULL DEFAULT 0,
    rejected_count INT NOT NULL DEFAULT 0,
    inserted_count INT NOT NULL DEFAULT 0,
    updated_count INT NOT NULL DEFAULT 0,
    unchanged_count INT NOT NULL DEFAULT 0,
    api_calls INT NOT NULL DEFAULT 0,
    progress_key VARCHAR(256) NULL,
    error_code VARCHAR(64) NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (run_id),
    KEY ix_runs_pipeline_status (pipeline_name, status, started_at),
    KEY ix_runs_started (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS api_quota_usage (
    quota_date DATE NOT NULL,
    api_name VARCHAR(128) NOT NULL,
    quota_limit INT NOT NULL,
    used_count INT NOT NULL DEFAULT 0,
    last_call_at DATETIME NULL,
    quota_status VARCHAR(32) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (quota_date, api_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
