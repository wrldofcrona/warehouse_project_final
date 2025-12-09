import psycopg2
from datetime import datetime
from contextlib import closing

OLTP_CONFIG = {
    "host": "localhost",
    "database": "warehouse_db",    
    "user": "postgres",
    "password": "postgres",
    "port": 5432,
}

DWH_CONFIG = {
    "host": "localhost",
    "database": "warehouse_dwh",   
    "user": "postgres",
    "password": "postgres",
    "port": 5432,
}


def get_conn(cfg):
    return psycopg2.connect(
        host=cfg["host"],
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        port=cfg["port"],
    )



def ensure_movement_types(cur_oltp, cur_dwh):
    """
    Загружаем все уникальные типы движений из OLTP в измерение dim_movement_type.
    """
    cur_oltp.execute("SELECT DISTINCT movement_type FROM inventory_movement")
    types = cur_oltp.fetchall()
    for (mt,) in types:
        cur_dwh.execute("""
            INSERT INTO dwh.dim_movement_type (movement_type)
            VALUES (%s)
            ON CONFLICT (movement_type) DO NOTHING
        """, (mt,))


def ensure_date(cur_dwh, dt):
    """
    Гарантируем, что дата dt есть в dim_date.
    Возвращаем date_key (формат YYYYMMDD).
    """
    date_key = int(dt.strftime("%Y%m%d"))
    cur_dwh.execute("SELECT 1 FROM dwh.dim_date WHERE date_key = %s", (date_key,))
    if cur_dwh.fetchone() is None:
        cur_dwh.execute("""
            INSERT INTO dwh.dim_date (date_key, full_date, year, month, day, quarter)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            date_key,
            dt.date(),
            dt.year,
            dt.month,
            dt.day,
            (dt.month - 1) // 3 + 1
        ))
    return date_key


def load_dim_products(cur_oltp, cur_dwh):
    """
    Загружаем справочник товаров в измерение dim_product.
    """
    cur_oltp.execute("""
        SELECT id, sku, name, category, min_quantity, max_quantity
        FROM product
    """)
    for row in cur_oltp.fetchall():
        product_id, sku, name, category, min_q, max_q = row
        cur_dwh.execute("""
            INSERT INTO dwh.dim_product (product_id, sku, name, category, min_quantity, max_quantity)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_id) DO UPDATE
            SET sku = EXCLUDED.sku,
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                min_quantity = EXCLUDED.min_quantity,
                max_quantity = EXCLUDED.max_quantity
        """, (product_id, sku, name, category, min_q, max_q))


def load_dim_warehouses(cur_oltp, cur_dwh):
    """
    Загружаем справочник складов в dim_warehouse.
    """
    cur_oltp.execute("""
        SELECT id, code, name, location, max_capacity
        FROM warehouse
    """)
    for row in cur_oltp.fetchall():
        warehouse_id, code, name, location, max_capacity = row
        cur_dwh.execute("""
            INSERT INTO dwh.dim_warehouse (warehouse_id, code, name, location, max_capacity)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (warehouse_id) DO UPDATE
            SET code = EXCLUDED.code,
                name = EXCLUDED.name,
                location = EXCLUDED.location,
                max_capacity = EXCLUDED.max_capacity
        """, (warehouse_id, code, name, location, max_capacity))


def load_dim_suppliers(cur_oltp, cur_dwh):
    """
    Загружаем справочник поставщиков в dim_supplier.
    """
    cur_oltp.execute("""
        SELECT id, name, contact_person, phone, rating
        FROM supplier
    """)
    for row in cur_oltp.fetchall():
        supplier_id, name, contact_person, phone, rating = row
        cur_dwh.execute("""
            INSERT INTO dwh.dim_supplier (supplier_id, name, contact_person, phone, rating)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (supplier_id) DO UPDATE
            SET name = EXCLUDED.name,
                contact_person = EXCLUDED.contact_person,
                phone = EXCLUDED.phone,
                rating = EXCLUDED.rating
        """, (supplier_id, name, contact_person, phone, rating))


def get_product_key(cur_dwh, product_id):
    cur_dwh.execute("SELECT product_key FROM dwh.dim_product WHERE product_id = %s", (product_id,))
    res = cur_dwh.fetchone()
    return res[0] if res else None


def get_warehouse_key(cur_dwh, warehouse_id):
    cur_dwh.execute("SELECT warehouse_key FROM dwh.dim_warehouse WHERE warehouse_id = %s", (warehouse_id,))
    res = cur_dwh.fetchone()
    return res[0] if res else None


def get_supplier_key(cur_dwh, supplier_id):
    if supplier_id is None:
        return None
    cur_dwh.execute("SELECT supplier_key FROM dwh.dim_supplier WHERE supplier_id = %s", (supplier_id,))
    res = cur_dwh.fetchone()
    return res[0] if res else None


def get_movement_type_key(cur_dwh, movement_type):
    cur_dwh.execute("SELECT movement_type_key FROM dwh.dim_movement_type WHERE movement_type = %s", (movement_type,))
    res = cur_dwh.fetchone()
    return res[0] if res else None


def load_fact_inventory_movements(cur_oltp, cur_dwh, full_reload=True):
    """
    Загружаем таблицу фактов fact_inventory_movement.
    full_reload=True: перед загрузкой очищаем таблицу фактов и грузим всё с нуля.
    Для учебного прототипа это нормально.
    """
    if full_reload:
        print("Очищаем таблицу фактов fact_inventory_movement...")
        cur_dwh.execute("DELETE FROM dwh.fact_inventory_movement")

    # Берём все движения из OLTP
    cur_oltp.execute("""
        SELECT im.id,
               im.product_id,
               im.warehouse_id,
               p.supplier_id,
               im.movement_type,
               im.quantity,
               im.unit_price,
               im.total_value,
               im.movement_date
        FROM inventory_movement im
        JOIN product p ON p.id = im.product_id
    """)
    rows = cur_oltp.fetchall()
    print(f"Найдено движений для загрузки: {len(rows)}")

    for (mov_id, product_id, warehouse_id, supplier_id,
         movement_type, quantity, unit_price, total_value, movement_date) in rows:

        if movement_date is None:
            movement_date = datetime.utcnow()

        # dim_date
        date_key = ensure_date(cur_dwh, movement_date)

        # dim_product
        product_key = get_product_key(cur_dwh, product_id)
        if product_key is None:
            continue

        # dim_warehouse
        warehouse_key = get_warehouse_key(cur_dwh, warehouse_id)
        if warehouse_key is None:
            continue

        # dim_supplier
        supplier_key = get_supplier_key(cur_dwh, supplier_id)

        # dim_movement_type
        movement_type_key = get_movement_type_key(cur_dwh, movement_type)
        if movement_type_key is None:
            cur_dwh.execute("""
                INSERT INTO dwh.dim_movement_type (movement_type)
                VALUES (%s)
                ON CONFLICT (movement_type) DO NOTHING
            """, (movement_type,))
            movement_type_key = get_movement_type_key(cur_dwh, movement_type)

        cur_dwh.execute("""
            INSERT INTO dwh.fact_inventory_movement
                (date_key, product_key, warehouse_key, supplier_key,
                 movement_type_key, quantity, unit_price, total_value, source_movement_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            date_key,
            product_key,
            warehouse_key,
            supplier_key,
            movement_type_key,
            quantity,
            unit_price,
            total_value,
            mov_id
        ))


def run_etl():
    """
    Главная функция ETL-процесса:
    1. Загружаем измерения.
    2. Загружаем факты.
    """
    with closing(get_conn(OLTP_CONFIG)) as conn_oltp, \
         closing(get_conn(DWH_CONFIG)) as conn_dwh:

        conn_oltp.autocommit = False
        conn_dwh.autocommit = False

        with conn_oltp.cursor() as cur_oltp, conn_dwh.cursor() as cur_dwh:
            print("Загружаем измерения...")
            load_dim_products(cur_oltp, cur_dwh)
            load_dim_warehouses(cur_oltp, cur_dwh)
            load_dim_suppliers(cur_oltp, cur_dwh)
            ensure_movement_types(cur_oltp, cur_dwh)

            print("Загружаем факты...")
            load_fact_inventory_movements(cur_oltp, cur_dwh, full_reload=True)

        conn_dwh.commit()
        conn_oltp.commit()
        print("ETL завершён успешно.")


if __name__ == "__main__":
    run_etl()
