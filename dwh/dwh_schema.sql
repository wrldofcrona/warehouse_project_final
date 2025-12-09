
CREATE SCHEMA IF NOT EXISTS dwh;

SET search_path TO dwh, public;



-- 1. Измерение дат
CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER PRIMARY KEY,   
    full_date    DATE NOT NULL,
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    day          INTEGER NOT NULL,
    quarter      INTEGER NOT NULL
);

-- 2. Измерение товаров
CREATE TABLE IF NOT EXISTS dim_product (
    product_key  SERIAL PRIMARY KEY,
    product_id   INTEGER UNIQUE,        
    sku          VARCHAR(50),
    name         VARCHAR(200),
    category     VARCHAR(100),
    min_quantity INTEGER,
    max_quantity INTEGER
);

-- 3. Измерение складов
CREATE TABLE IF NOT EXISTS dim_warehouse (
    warehouse_key SERIAL PRIMARY KEY,
    warehouse_id  INTEGER UNIQUE,       
    code          VARCHAR(20),
    name          VARCHAR(100),
    location      VARCHAR(200),
    max_capacity  INTEGER
);

-- 4. Измерение поставщиков
CREATE TABLE IF NOT EXISTS dim_supplier (
    supplier_key SERIAL PRIMARY KEY,
    supplier_id  INTEGER UNIQUE,        
    name         VARCHAR(200),
    contact_person VARCHAR(100),
    phone        VARCHAR(50),
    rating       NUMERIC(3,1)
);

-- 5. Измерение типа движения
CREATE TABLE IF NOT EXISTS dim_movement_type (
    movement_type_key SERIAL PRIMARY KEY,
    movement_type     VARCHAR(50) UNIQUE  
);



CREATE TABLE IF NOT EXISTS fact_inventory_movement (
    movement_key      BIGSERIAL PRIMARY KEY,
    
    date_key          INTEGER NOT NULL,
    product_key       INTEGER NOT NULL,
    warehouse_key     INTEGER NOT NULL,
    supplier_key      INTEGER,
    movement_type_key INTEGER NOT NULL,

    quantity          INTEGER,
    unit_price        NUMERIC(10,2),
    total_value       NUMERIC(10,2),

    source_movement_id INTEGER,
    
    CONSTRAINT fk_fact_date
        FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_fact_product
        FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_fact_warehouse
        FOREIGN KEY (warehouse_key) REFERENCES dim_warehouse (warehouse_key),
    CONSTRAINT fk_fact_supplier
        FOREIGN KEY (supplier_key) REFERENCES dim_supplier (supplier_key),
    CONSTRAINT fk_fact_mtype
        FOREIGN KEY (movement_type_key) REFERENCES dim_movement_type (movement_type_key)
);


CREATE INDEX IF NOT EXISTS idx_fact_date ON fact_inventory_movement(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_product ON fact_inventory_movement(product_key);
CREATE INDEX IF NOT EXISTS idx_fact_warehouse ON fact_inventory_movement(warehouse_key);
CREATE INDEX IF NOT EXISTS idx_fact_mtype ON fact_inventory_movement(movement_type_key);
