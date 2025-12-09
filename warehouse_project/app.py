from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
import json
import os
import warnings
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, text, func, case
import psycopg2
from decimal import Decimal

warnings.filterwarnings('ignore')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'warehouse-management-system-2024'

#  КОНФИГУРАЦИЯ POSTGRESQL 
POSTGRES_CONFIG = {
    'host': 'localhost',
    'database': 'warehouse_db',
    'user': 'postgres',
    'password': 'postgres',  
    'port': '5432'
}


DATABASE_URL = f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}"
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

#  ПОДКЛЮЧЕНИЕ К DWH 
def get_dwh_connection():
    try:
        return psycopg2.connect(
            host="localhost",
            database="warehouse_dwh",   
            user="postgres",
            password="postgres",
            port=5432
        )
    except Exception as e:
        print(f"Ошибка подключения к DWH: {e}")
        return None


#  МОДЕЛИ БАЗЫ ДАННЫХ 

class Warehouse(db.Model):
    """Модель склада"""
    __tablename__ = 'warehouse'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200))
    max_capacity = db.Column(db.Integer, default=10000)
    current_capacity = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    products = db.relationship('Product', backref='warehouse', lazy=True)
    movements = db.relationship('InventoryMovement', backref='warehouse', lazy=True)
    
    def __repr__(self):
        return f'<Warehouse {self.code}: {self.name}>'

class Category(db.Model):
    """Модель категории товаров"""
    __tablename__ = 'category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    
    products = db.relationship('Product', backref='category_rel', lazy=True)
    
    def __repr__(self):
        return f'<Category {self.name}>'

class Product(db.Model):
    """Модель товара"""
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    category = db.Column(db.String(100))
    unit_price = db.Column(db.Numeric(10, 2), default=0.00)
    cost_price = db.Column(db.Numeric(10, 2), default=0.00)
    quantity = db.Column(db.Integer, default=0)
    min_quantity = db.Column(db.Integer, default=10)
    max_quantity = db.Column(db.Integer, default=100)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    movements = db.relationship('InventoryMovement', backref='product_rel', lazy=True)
    
    def __repr__(self):
        return f'<Product {self.sku}: {self.name}>'
    
    @property
    def total_value(self):
        return float(self.quantity) * float(self.unit_price) if self.unit_price else 0
    
    @property
    def stock_status(self):
        if self.quantity == 0:
            return 'out-of-stock'
        elif self.quantity <= self.min_quantity:
            return 'danger'
        elif self.quantity <= self.min_quantity * 1.5:
            return 'warning'
        else:
            return 'success'

class Supplier(db.Model):
    """Модель поставщика"""
    __tablename__ = 'supplier'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(200), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    rating = db.Column(db.Numeric(3, 1), default=5.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    products = db.relationship('Product', backref='supplier', lazy=True)
    purchases = db.relationship('PurchaseOrder', backref='supplier', lazy=True)
    
    def __repr__(self):
        return f'<Supplier {self.code}: {self.name}>'

class InventoryMovement(db.Model):
    """Модель движения товаров"""
    __tablename__ = 'inventory_movement'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'), nullable=False)
    movement_type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2))
    total_value = db.Column(db.Numeric(10, 2))
    document_number = db.Column(db.String(100))
    reference = db.Column(db.String(200))
    movement_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    created_by = db.Column(db.String(100))
    
    product = db.relationship('Product', backref='movement_history')
    
    def __repr__(self):
        return f'<Movement {self.movement_type}: {self.quantity} units>'

class PurchaseOrder(db.Model):
    """Модель заказа на поставку"""
    __tablename__ = 'purchase_order'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_date = db.Column(db.DateTime)
    received_date = db.Column(db.DateTime)
    status = db.Column(db.String(50), default='pending')
    notes = db.Column(db.Text)
    
    product = db.relationship('Product')
    
    def __repr__(self):
        return f'<PurchaseOrder {self.order_number}>'

# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ 

def get_db_connection():
    """Создание прямого соединения с PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_CONFIG['host'],
            database=POSTGRES_CONFIG['database'],
            user=POSTGRES_CONFIG['user'],
            password=POSTGRES_CONFIG['password'],
            port=POSTGRES_CONFIG['port']
        )
        return conn
    except Exception as e:
        print(f"Ошибка подключения к PostgreSQL: {e}")
        return None

def create_tables():
    """Создание таблиц через SQL"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Создание таблицы складов
        cur.execute('''
            CREATE TABLE IF NOT EXISTS warehouse (
                id SERIAL PRIMARY KEY,
                code VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                location VARCHAR(200),
                max_capacity INTEGER DEFAULT 10000,
                current_capacity INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создание таблицы категорий
        cur.execute('''
            CREATE TABLE IF NOT EXISTS category (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT
            )
        ''')
        
        # Создание таблицы поставщиков
        cur.execute('''
            CREATE TABLE IF NOT EXISTS supplier (
                id SERIAL PRIMARY KEY,
                code VARCHAR(20) UNIQUE,
                name VARCHAR(200) NOT NULL,
                contact_person VARCHAR(100),
                phone VARCHAR(50),
                email VARCHAR(100),
                address TEXT,
                rating NUMERIC(3,1) DEFAULT 5.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создание таблицы товаров
        cur.execute('''
            CREATE TABLE IF NOT EXISTS product (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                category_id INTEGER REFERENCES category(id),
                category VARCHAR(100),
                unit_price NUMERIC(10,2) DEFAULT 0.00,
                cost_price NUMERIC(10,2) DEFAULT 0.00,
                quantity INTEGER DEFAULT 0,
                min_quantity INTEGER DEFAULT 10,
                max_quantity INTEGER DEFAULT 100,
                warehouse_id INTEGER REFERENCES warehouse(id),
                supplier_id INTEGER REFERENCES supplier(id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создание таблицы движений товаров
        cur.execute('''
            CREATE TABLE IF NOT EXISTS inventory_movement (
                id SERIAL PRIMARY KEY,
                product_id INTEGER REFERENCES product(id) NOT NULL,
                warehouse_id INTEGER REFERENCES warehouse(id) NOT NULL,
                movement_type VARCHAR(50) NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price NUMERIC(10,2),
                total_value NUMERIC(10,2),
                document_number VARCHAR(100),
                reference VARCHAR(200),
                movement_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                created_by VARCHAR(100)
            )
        ''')
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Таблицы созданы успешно")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}")
        conn.rollback()
        return False

def create_chart_base64(fig):
    """Преобразует график matplotlib в base64 для HTML"""
    try:
        img = io.BytesIO()
        fig.savefig(img, format='png', bbox_inches='tight', dpi=100)
        img.seek(0)
        return base64.b64encode(img.getvalue()).decode()
    except Exception as e:
        print(f"Ошибка при создании графика: {e}")
        return ""

def safe_tight_layout(fig):
    """Безопасное использование tight_layout с обработкой ошибок"""
    try:
        fig.tight_layout()
    except Exception:
        fig.subplots_adjust(left=0.15, right=0.9, top=0.9, bottom=0.15)

def calculate_warehouse_stats():
    """Расчет статистики складов"""
    stats = {}
    warehouses = Warehouse.query.all()
    
    for warehouse in warehouses:
        products = Product.query.filter_by(warehouse_id=warehouse.id).all()
        total_quantity = sum(p.quantity for p in products)
        
        total_value = 0
        for p in products:
            try:
                if p.unit_price:
                    total_value += float(p.quantity) * float(p.unit_price)
            except (ValueError, TypeError):
                continue
        
        low_stock = sum(1 for p in products if p.quantity <= p.min_quantity)
        
        capacity_percent = 0
        if warehouse.max_capacity and warehouse.max_capacity > 0:
            capacity_percent = min(100, (total_quantity / warehouse.max_capacity * 100))
        
        stats[warehouse.id] = {
            'id': warehouse.id,
            'code': warehouse.code,
            'name': warehouse.name,
            'total_products': len(products),
            'total_quantity': total_quantity,
            'total_value': total_value,
            'low_stock_count': low_stock,
            'capacity_percent': capacity_percent,
            'location': warehouse.location
        }
    
    return stats

def get_low_stock_products(limit=20):
    """Товары с низким запасом"""
    products = Product.query.filter(
        Product.quantity <= Product.min_quantity
    ).order_by(Product.quantity).limit(limit).all()
    
    low_stock = []
    for product in products:
        low_stock.append({
            'id': product.id,
            'sku': product.sku,
            'name': product.name,
            'category': product.category,
            'current': product.quantity,
            'min': product.min_quantity,
            'warehouse': product.warehouse.name if product.warehouse else 'Не указан',
            'unit_price': float(product.unit_price) if product.unit_price else 0,
            'total_value': product.total_value,
            'status': product.stock_status
        })
    
    return low_stock

def get_recent_movements(limit=10):
    """Последние движения товаров"""
    movements = InventoryMovement.query.order_by(
        InventoryMovement.movement_date.desc()
    ).limit(limit).all()
    
    return movements

def generate_daily_report():
    """Генерация ежедневного отчета"""
    today = date.today()
    
    # Движения за сегодня
    movements_today = InventoryMovement.query.filter(
        db.func.date(InventoryMovement.movement_date) == today
    ).all()
    
    # Новые товары
    new_products = Product.query.filter(
        db.func.date(Product.created_at) == today
    ).count()
    
    # Общая статистика
    total_products = Product.query.count()
    total_warehouses = Warehouse.query.count()
    total_suppliers = Supplier.query.count()
    
    # Суммарная стоимость
    products = Product.query.all()
    total_value = 0
    for p in products:
        try:
            if p.unit_price:
                total_value += float(p.quantity) * float(p.unit_price)
        except (ValueError, TypeError):
            continue
    
    return {
        'date': today.strftime('%d.%m.%Y'),
        'movements_count': len(movements_today),
        'new_products': new_products,
        'total_products': total_products,
        'total_warehouses': total_warehouses,
        'total_suppliers': total_suppliers,
        'total_value': total_value,
        'movements': movements_today[:5]
    }

# РОУТЫ 

@app.route('/')
def index():
    """Главная страница - дашборд"""
    try:
        # Общая статистика
        total_products = Product.query.count()
        total_warehouses = Warehouse.query.count()
        total_movements = InventoryMovement.query.count()
        total_suppliers = Supplier.query.count()
        
        # Статистика складов
        warehouse_stats = calculate_warehouse_stats()
        
        # Товары с низким запасом
        low_stock = get_low_stock_products(10)
        
        # Последние движения
        recent_movements = get_recent_movements(10)
        
        # Ежедневный отчет
        daily_report = generate_daily_report()
        
        # Распределение по категориям
        categories_result = db.session.query(
            Product.category,
            db.func.count(Product.id).label('count'),
            db.func.sum(Product.quantity).label('total_quantity'),
            db.func.sum(Product.quantity * Product.unit_price).label('total_value')
        ).group_by(Product.category).all()
        
        categories = []
        for cat, count, total_qty, total_val in categories_result:
            categories.append({
                'category': cat,
                'count': count,
                'total_quantity': total_qty or 0,
                'total_value': float(total_val or 0)
            })
        
        return render_template('dashboard.html',
                             total_products=total_products,
                             total_warehouses=total_warehouses,
                             total_movements=total_movements,
                             total_suppliers=total_suppliers,
                             low_stock=low_stock,
                             recent_movements=recent_movements,
                             warehouse_stats=warehouse_stats,
                             daily_report=daily_report,
                             categories=categories)
    except Exception as e:
        print(f"Ошибка на главной странице: {e}")
        return render_template('error.html', 
                             error='Ошибка загрузки данных',
                             message=str(e))

@app.route('/products')
def products():
    """Страница со списком товаров"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Фильтры
        category_filter = request.args.get('category', '')
        warehouse_filter = request.args.get('warehouse', '')
        search_query = request.args.get('search', '')
        stock_status = request.args.get('stock_status', '')
        
        # Базовый запрос
        query = Product.query
        
        if search_query:
            query = query.filter(
                db.or_(
                    Product.name.ilike(f'%{search_query}%'),
                    Product.sku.ilike(f'%{search_query}%'),
                    Product.description.ilike(f'%{search_query}%')
                )
            )
        
        if category_filter:
            query = query.filter_by(category=category_filter)
        
        if warehouse_filter:
            query = query.filter_by(warehouse_id=warehouse_filter)
        
        if stock_status:
            if stock_status == 'low':
                query = query.filter(Product.quantity <= Product.min_quantity)
            elif stock_status == 'out':
                query = query.filter(Product.quantity == 0)
            elif stock_status == 'normal':
                query = query.filter(Product.quantity > Product.min_quantity)
        
        # Пагинация
        products_paginated = query.order_by(Product.name).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Данные для фильтров
        categories = db.session.query(Product.category).distinct().all()
        warehouses = Warehouse.query.all()
        
        return render_template('products.html',
                             products=products_paginated,
                             categories=[c[0] for c in categories if c[0]],
                             warehouses=warehouses,
                             current_filters={
                                 'category': category_filter,
                                 'warehouse': warehouse_filter,
                                 'search': search_query,
                                 'stock_status': stock_status
                             })
    except Exception as e:
        print(f"Ошибка в products: {e}")
        flash(f'Ошибка: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/products/add', methods=['GET', 'POST'])
def add_product():
    """Добавление нового товара"""
    try:
        if request.method == 'POST':
            sku = request.form['sku'].strip()
            
            if Product.query.filter_by(sku=sku).first():
                flash('Товар с таким SKU уже существует!', 'danger')
                return redirect(url_for('add_product'))
            
            warehouse_id = request.form.get('warehouse_id')
            quantity = int(request.form.get('quantity', 0) or 0)
            unit_price = float(request.form.get('unit_price', 0) or 0)
            
            # Создаем товар
            product = Product(
                sku=sku,
                name=request.form['name'].strip(),
                description=request.form.get('description', '').strip(),
                category=request.form.get('category', '').strip(),
                unit_price=unit_price,
                cost_price=float(request.form.get('cost_price', 0) or 0),
                quantity=quantity,
                min_quantity=int(request.form.get('min_quantity', 10) or 10),
                max_quantity=int(request.form.get('max_quantity', 100) or 100),
                warehouse_id=int(warehouse_id) if warehouse_id else None,
                supplier_id=int(request.form['supplier_id']) if request.form.get('supplier_id') else None
            )
            
            # Добавляем товар и получаем ID
            db.session.add(product)
            db.session.flush()  # Получаем ID без коммита
            
            # Создаем движение
            if quantity > 0 and warehouse_id:
                movement = InventoryMovement(
                    product_id=product.id,  
                    warehouse_id=int(warehouse_id),
                    movement_type='in',
                    quantity=quantity,
                    unit_price=unit_price,
                    total_value=quantity * unit_price,
                    document_number='INITIAL',
                    notes='Начальный остаток',
                    created_by='system'
                )
                db.session.add(movement)
            
            # Коммитим все изменения
            db.session.commit()
            
            flash(f'Товар "{product.name}" успешно добавлен!', 'success')
            return redirect(url_for('products'))
        
        warehouses = Warehouse.query.all()
        suppliers = Supplier.query.all()
        categories = db.session.query(Product.category).distinct().all()
        
        return render_template('add_product.html',
                             warehouses=warehouses,
                             suppliers=suppliers,
                             categories=[c[0] for c in categories if c[0]])
        
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при добавлении товара: {str(e)}', 'danger')
        return redirect(url_for('add_product'))

@app.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
def edit_product(product_id):
    """Редактирование товара"""
    try:
        product = Product.query.get_or_404(product_id)
        
        if request.method == 'POST':
            old_quantity = product.quantity
            
            product.name = request.form['name'].strip()
            product.description = request.form.get('description', '').strip()
            product.category = request.form['category'].strip()
            product.unit_price = float(request.form.get('unit_price', 0))
            product.cost_price = float(request.form.get('cost_price', 0))
            product.min_quantity = int(request.form.get('min_quantity', 10))
            product.max_quantity = int(request.form.get('max_quantity', 100))
            product.warehouse_id = int(request.form['warehouse_id']) if request.form.get('warehouse_id') else None
            product.supplier_id = int(request.form['supplier_id']) if request.form.get('supplier_id') else None
            product.updated_at = datetime.utcnow()
            
            new_quantity = int(request.form.get('quantity', 0))
            if new_quantity != old_quantity and product.warehouse_id:
                diff = new_quantity - old_quantity
                movement_type = 'in' if diff > 0 else 'out'
                
                movement = InventoryMovement(
                    product_id=product.id,
                    warehouse_id=product.warehouse_id,
                    movement_type=movement_type,
                    quantity=abs(diff),
                    unit_price=product.unit_price,
                    total_value=abs(diff) * float(product.unit_price),
                    document_number='ADJUSTMENT',
                    notes=f'Корректировка количества с {old_quantity} на {new_quantity}',
                    created_by='system'
                )
                db.session.add(movement)
                
                product.quantity = new_quantity
            
            db.session.commit()
            
            flash(f'Товар "{product.name}" успешно обновлен!', 'success')
            return redirect(url_for('products'))
        
        warehouses = Warehouse.query.all()
        suppliers = Supplier.query.all()
        categories = db.session.query(Product.category).distinct().all()
        
        return render_template('edit_product.html',
                             product=product,
                             warehouses=warehouses,
                             suppliers=suppliers,
                             categories=[c[0] for c in categories if c[0]])
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при обновлении товара: {str(e)}', 'danger')
        return redirect(url_for('edit_product', product_id=product_id))

@app.route('/products/<int:product_id>/delete', methods=['POST'])
def delete_product(product_id):
    """Удаление товара"""
    try:
        product = Product.query.get_or_404(product_id)
        
        InventoryMovement.query.filter_by(product_id=product_id).delete()
        
        db.session.delete(product)
        db.session.commit()
        flash(f'Товар "{product.name}" успешно удален!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении товара: {str(e)}', 'danger')
    
    return redirect(url_for('products'))

@app.route('/movements')
def movements():
    """Страница движений товаров"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Фильтры
        movement_type = request.args.get('type', '')
        product_id = request.args.get('product', '')
        warehouse_id = request.args.get('warehouse', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        
        query = InventoryMovement.query.join(Product)
        
        if movement_type:
            query = query.filter_by(movement_type=movement_type)
        
        if product_id:
            query = query.filter_by(product_id=product_id)
        
        if warehouse_id:
            query = query.filter_by(warehouse_id=warehouse_id)
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(InventoryMovement.movement_date >= date_from_obj)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                date_to_obj += timedelta(days=1)
                query = query.filter(InventoryMovement.movement_date <= date_to_obj)
            except ValueError:
                pass
        
        movements_paginated = query.order_by(
            InventoryMovement.movement_date.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        products = Product.query.all()
        warehouses = Warehouse.query.all()
        
        return render_template('movements.html',
                             movements=movements_paginated,
                             products=products,
                             warehouses=warehouses,
                             current_filters={
                                 'type': movement_type,
                                 'product': product_id,
                                 'warehouse': warehouse_id,
                                 'date_from': date_from,
                                 'date_to': date_to
                             })
    except Exception as e:
        print(f"Ошибка в movements: {e}")
        flash(f'Ошибка: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/movements/add', methods=['GET', 'POST'])
def add_movement():
    """Добавление движения товара"""
    try:
        if request.method == 'POST':
            product_id = int(request.form['product_id'])
            movement_type = request.form['movement_type']
            quantity = int(request.form['quantity'])
            warehouse_id = int(request.form.get('warehouse_id', 0))
            document_number = request.form.get('document_number', '').strip()
            notes = request.form.get('notes', '').strip()
            
            product = Product.query.get_or_404(product_id)
            
            if warehouse_id:
                target_warehouse_id = warehouse_id
            else:
                target_warehouse_id = product.warehouse_id
                
            if not target_warehouse_id:
                flash('Не указан склад для движения!', 'danger')
                return redirect(url_for('add_movement'))
            
            if movement_type == 'out' and product.quantity < quantity:
                flash(f'Недостаточно товара на складе! Доступно: {product.quantity}', 'danger')
                return redirect(url_for('add_movement'))
            
            movement = InventoryMovement(
                product_id=product_id,
                warehouse_id=target_warehouse_id,
                movement_type=movement_type,
                quantity=quantity,
                unit_price=float(product.unit_price),
                total_value=quantity * float(product.unit_price),
                document_number=document_number,
                notes=notes,
                created_by='user',
                movement_date=datetime.utcnow()
            )
            
            if movement_type == 'in':
                product.quantity += quantity
                if warehouse_id and warehouse_id != product.warehouse_id:
                    product.warehouse_id = warehouse_id
            elif movement_type == 'out':
                product.quantity -= quantity
            
            product.updated_at = datetime.utcnow()
            
            db.session.add(movement)
            db.session.commit()
            
            flash(f'Движение товара успешно добавлено!', 'success')
            return redirect(url_for('movements'))
        
        products = Product.query.all()
        warehouses = Warehouse.query.all()
        return render_template('add_movement.html', 
                             products=products, 
                             warehouses=warehouses)
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при добавлении движения: {str(e)}', 'danger')
        return redirect(url_for('add_movement'))

@app.route('/warehouses')
def warehouses():
    """Управление складами"""
    try:
        all_warehouses = Warehouse.query.all()
        
        warehouses_data = []
        for warehouse in all_warehouses:
            products = Product.query.filter_by(warehouse_id=warehouse.id).all()
            
            product_count = len(products)
            total_quantity = sum(p.quantity for p in products)
            total_value = 0
            for p in products:
                try:
                    if p.unit_price:
                        total_value += float(p.quantity) * float(p.unit_price)
                except (ValueError, TypeError):
                    continue
            
            low_stock = sum(1 for p in products if p.quantity <= p.min_quantity)
            
            if warehouse.max_capacity > 0:
                current_capacity = min(100, (total_quantity / warehouse.max_capacity) * 100)
            else:
                current_capacity = 0
            
            warehouse_data = {
                'id': warehouse.id,
                'code': warehouse.code,
                'name': warehouse.name,
                'location': warehouse.location,
                'max_capacity': warehouse.max_capacity,
                'created_at': warehouse.created_at,
                
                'product_count': product_count,
                'total_quantity': total_quantity,
                'total_value': total_value,
                'low_stock': low_stock,
                'current_capacity': current_capacity
            }
            
            warehouses_data.append(warehouse_data)
        
        return render_template('warehouses.html', warehouses=warehouses_data)
    except Exception as e:
        print(f"Ошибка в warehouses: {e}")
        flash(f'Ошибка: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/warehouses/add', methods=['GET', 'POST'])
def add_warehouse():
    """Добавление нового склада"""
    try:
        if request.method == 'POST':
            code = request.form['code'].strip()
            if Warehouse.query.filter_by(code=code).first():
                flash('Склад с таким кодом уже существует!', 'danger')
                return redirect(url_for('add_warehouse'))
            
            warehouse = Warehouse(
                code=code,
                name=request.form['name'].strip(),
                location=request.form['location'].strip(),
                max_capacity=int(request.form.get('max_capacity', 10000))
            )
            
            db.session.add(warehouse)
            db.session.commit()
            
            flash(f'Склад "{warehouse.name}" успешно добавлен!', 'success')
            return redirect(url_for('warehouses'))
        
        return render_template('add_warehouse.html')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при добавлении склада: {str(e)}', 'danger')
        return redirect(url_for('add_warehouse'))

@app.route('/warehouses/<int:warehouse_id>/edit', methods=['GET', 'POST'])
def edit_warehouse(warehouse_id):
    """Редактирование склада"""
    try:
        warehouse = Warehouse.query.get_or_404(warehouse_id)
        
        if request.method == 'POST':
            warehouse.name = request.form['name'].strip()
            warehouse.location = request.form['location'].strip()
            warehouse.max_capacity = int(request.form.get('max_capacity', 10000))
            
            db.session.commit()
            
            flash(f'Склад "{warehouse.name}" успешно обновлен!', 'success')
            return redirect(url_for('warehouses'))
        
        return render_template('edit_warehouse.html', warehouse=warehouse)
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при обновлении склада: {str(e)}', 'danger')
        return redirect(url_for('edit_warehouse', warehouse_id=warehouse_id))

@app.route('/warehouses/<int:warehouse_id>/delete', methods=['POST'])
def delete_warehouse(warehouse_id):
    """Удаление склада"""
    try:
        warehouse = Warehouse.query.get_or_404(warehouse_id)
        
        products_count = Product.query.filter_by(warehouse_id=warehouse_id).count()
        if products_count > 0:
            flash(f'Невозможно удалить склад! На складе есть {products_count} товаров.', 'danger')
            return redirect(url_for('warehouses'))
        
        db.session.delete(warehouse)
        db.session.commit()
        flash(f'Склад "{warehouse.name}" успешно удален!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении склада: {str(e)}', 'danger')
    
    return redirect(url_for('warehouses'))

@app.route('/suppliers')
def suppliers():
    """Управление поставщиками"""
    try:
        all_suppliers = Supplier.query.all()
        
        for supplier in all_suppliers:
            supplier.product_count = Product.query.filter_by(supplier_id=supplier.id).count()
            supplier.order_count = 0  # Можно добавить логику подсчета заказов
        
        return render_template('suppliers.html', suppliers=all_suppliers)
    except Exception as e:
        print(f"Ошибка в suppliers: {e}")
        flash(f'Ошибка: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/suppliers/add', methods=['GET', 'POST'])
def add_supplier():
    """Добавление нового поставщика"""
    try:
        if request.method == 'POST':
            code = request.form['code'].strip()
            if Supplier.query.filter_by(code=code).first():
                flash('Поставщик с таким кодом уже существует!', 'danger')
                return redirect(url_for('add_supplier'))
            
            supplier = Supplier(
                code=code,
                name=request.form['name'].strip(),
                contact_person=request.form.get('contact_person', '').strip(),
                phone=request.form.get('phone', '').strip(),
                email=request.form.get('email', '').strip(),
                address=request.form.get('address', '').strip()
            )
            
            db.session.add(supplier)
            db.session.commit()
            
            flash(f'Поставщик "{supplier.name}" успешно добавлен!', 'success')
            return redirect(url_for('suppliers'))
        
        return render_template('add_supplier.html')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при добавлении поставщика: {str(e)}', 'danger')
        return redirect(url_for('add_supplier'))

@app.route('/suppliers/<int:supplier_id>/edit', methods=['GET', 'POST'])
def edit_supplier(supplier_id):
    """Редактирование поставщика"""
    try:
        supplier = Supplier.query.get_or_404(supplier_id)
        
        if request.method == 'POST':
            supplier.name = request.form['name'].strip()
            supplier.contact_person = request.form.get('contact_person', '').strip()
            supplier.phone = request.form.get('phone', '').strip()
            supplier.email = request.form.get('email', '').strip()
            supplier.address = request.form.get('address', '').strip()
            supplier.rating = float(request.form.get('rating', 5.0))
            
            db.session.commit()
            
            flash(f'Поставщик "{supplier.name}" успешно обновлен!', 'success')
            return redirect(url_for('suppliers'))
        
        return render_template('edit_supplier.html', supplier=supplier)
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при обновлении поставщика: {str(e)}', 'danger')
        return redirect(url_for('edit_supplier', supplier_id=supplier_id))

@app.route('/suppliers/<int:supplier_id>/delete', methods=['POST'])
def delete_supplier(supplier_id):
    """Удаление поставщика"""
    try:
        supplier = Supplier.query.get_or_404(supplier_id)
        
        products_count = Product.query.filter_by(supplier_id=supplier_id).count()
        if products_count > 0:
            flash(f'Невозможно удалить поставщика! С ним связано {products_count} товаров.', 'danger')
            return redirect(url_for('suppliers'))
        
        db.session.delete(supplier)
        db.session.commit()
        flash(f'Поставщик "{supplier.name}" успешно удален!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении поставщика: {str(e)}', 'danger')
    
    return redirect(url_for('suppliers'))

@app.route('/reports')
def reports():
    """Страница отчетов с графиками"""
    try:
        products = Product.query.all()
        warehouses = Warehouse.query.all()
        suppliers = Supplier.query.all()
        movements = InventoryMovement.query.all()
        
        # Основная статистика
        total_products = len(products)
        total_warehouses = len(warehouses)
        total_suppliers = len(suppliers)
        
        # Статистика складов
        warehouse_stats = calculate_warehouse_stats()
        
        # Товары с низким запасом
        low_stock = get_low_stock_products(20)
        
        # Топ товаров
        top_products_by_value = sorted(
            products, 
            key=lambda x: x.total_value, 
            reverse=True
        )[:10]
        
        top_products_by_quantity = sorted(
            products, 
            key=lambda x: x.quantity, 
            reverse=True
        )[:10]
        
        # ГЕНЕРАЦИЯ ГРАФИКОВ 
        
        # 1. Распределение товаров по категориям
        chart1 = ""
        try:
            # Группируем по категориям
            categories_data = {}
            for product in products:
                category = product.category or 'Без категории'
                if category not in categories_data:
                    categories_data[category] = {'count': 0, 'value': 0}
                categories_data[category]['count'] += 1
                categories_data[category]['value'] += product.total_value
            
            # Сортируем по стоимости
            sorted_categories = sorted(categories_data.items(), 
                                     key=lambda x: x[1]['value'], 
                                     reverse=True)
            
            # Берем топ-8 категорий, остальные группируем как "Другие"
            top_categories = sorted_categories[:8]
            other_value = sum(cat[1]['value'] for cat in sorted_categories[8:])
            other_count = sum(cat[1]['count'] for cat in sorted_categories[8:])
            
            if other_value > 0:
                top_categories.append(('Другие', {'count': other_count, 'value': other_value}))
            
            fig1, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
            
            # Круговая диаграмма по количеству товаров
            labels1 = [cat[0] for cat in top_categories]
            sizes1 = [cat[1]['count'] for cat in top_categories]
            
            ax1.pie(sizes1, labels=labels1, autopct='%1.1f%%', startangle=90)
            ax1.set_title('Распределение товаров по категориям (количество)', fontsize=14)
            ax1.axis('equal')
            
            # Круговая диаграмма по стоимости
            labels2 = [cat[0] for cat in top_categories]
            sizes2 = [cat[1]['value'] for cat in top_categories]
            
            ax2.pie(sizes2, labels=labels2, autopct='%1.1f%%', startangle=90)
            ax2.set_title('Распределение товаров по категориям (стоимость)', fontsize=14)
            ax2.axis('equal')
            
            plt.tight_layout()
            chart1 = create_chart_base64(fig1)
            plt.close(fig1)
        except Exception as e:
            print(f"Ошибка при генерации chart1: {e}")
            chart1 = ""
        
        # 2. Заполненность складов
        chart2 = ""
        try:
            fig2, ax = plt.subplots(figsize=(12, 6))
            
            warehouse_names = []
            capacities = []
            values = []
            colors = []
            
            for stats in warehouse_stats.values():
                warehouse_names.append(stats['name'])
                capacities.append(stats['capacity_percent'])
                values.append(stats['total_value'])
                
                if stats['capacity_percent'] < 60:
                    colors.append('#28a745')  # зеленый
                elif stats['capacity_percent'] < 80:
                    colors.append('#ffc107')  # желтый
                else:
                    colors.append('#dc3545')  # красный
            
            # Создаем диаграмму
            bars = ax.bar(warehouse_names, capacities, color=colors, alpha=0.7)
            ax.set_xlabel('Склады', fontsize=12)
            ax.set_ylabel('Заполненность (%)', fontsize=12)
            ax.set_title('Заполненность складов', fontsize=16, fontweight='bold')
            ax.set_ylim(0, 100)
            ax.grid(axis='y', alpha=0.3)
            
            # Добавляем значения на столбцы
            for bar, val in zip(bars, capacities):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                       f'{val:.1f}%', ha='center', va='bottom', fontsize=10)
            
           
            plt.tight_layout()
            chart2 = create_chart_base64(fig2)
            plt.close(fig2)
        except Exception as e:
            print(f"Ошибка при генерации chart2: {e}")
            chart2 = ""
        
        # 3. Динамика движений товаров (30 дней)
        chart3 = ""
        try:
            thirty_days_ago = datetime.now() - timedelta(days=30)
            recent_movements = InventoryMovement.query.filter(
                InventoryMovement.movement_date >= thirty_days_ago
            ).all()
            
            fig3, ax = plt.subplots(figsize=(14, 6))
            
            if not recent_movements:
                ax.text(0.5, 0.5, 'Нет данных о движениях\nза последние 30 дней', 
                        ha='center', va='center', fontsize=14)
                ax.set_title('Динамика движений товаров', fontsize=16)
            else:
                # Подготовка данных
                dates_dict = {}
                for i in range(30):
                    date = (datetime.now() - timedelta(days=i)).date()
                    dates_dict[date] = {'in': 0, 'out': 0}
                
                for movement in recent_movements:
                    day = movement.movement_date.date()
                    if day in dates_dict:
                        if movement.movement_type == 'in':
                            dates_dict[day]['in'] += movement.quantity
                        elif movement.movement_type == 'out':
                            dates_dict[day]['out'] += movement.quantity
                
                # Сортируем
                sorted_dates = sorted(dates_dict.items())
                date_labels = [d[0].strftime('%d.%m') for d in sorted_dates]
                net_values = [d[1]['in'] - d[1]['out'] for d in sorted_dates]

                # Сглаживание
                window = 3
                smoothed = []
                for i in range(len(net_values)):
                    start = max(0, i - window + 1)
                    end = i + 1
                    smoothed.append(sum(net_values[start:end]) / (end - start))
                
                x = range(len(date_labels))
                
                # График
                ax.plot(x, smoothed, color='#0d6efd', linewidth=3, 
                    marker='o', markersize=5, label='Нетто-оборот')
                
                
                ax.fill_between(x, smoothed, 0, 
                            where=[v >= 0 for v in smoothed], 
                            color='#28a745', alpha=0.3)
                ax.fill_between(x, smoothed, 0, 
                            where=[v < 0 for v in smoothed], 
                            color='#dc3545', alpha=0.3)
                
                # Настройки
                ax.set_xlabel('Дата', fontsize=12)
                ax.set_ylabel('Нетто-оборот (ед.)', fontsize=12)
                ax.set_title('Динамика движений товаров (последние 30 дней)', 
                            fontsize=16, fontweight='bold')
                
                # Подписи дат
                step = max(1, len(x) // 8)
                ax.set_xticks(x[::step])
                ax.set_xticklabels([date_labels[i] for i in x[::step]], rotation=45, ha='right')
                
                ax.legend()
                ax.grid(True, alpha=0.2)
                ax.axhline(y=0, color='black', linewidth=1, alpha=0.5)
            
            plt.tight_layout()
            chart3 = create_chart_base64(fig3)
            plt.close(fig3)
            
        except Exception as e:
            print(f"Ошибка при генерации chart3: {e}")
            chart3 = ""
        
        return render_template('reports.html',
                             total_products=total_products,
                             total_warehouses=total_warehouses,
                             total_suppliers=total_suppliers,
                             top_products_by_value=top_products_by_value,
                             top_products_by_quantity=top_products_by_quantity,
                             low_stock=low_stock,
                             warehouse_stats=warehouse_stats,
                             chart1=chart1,
                             chart2=chart2,
                             chart3=chart3)
        
    except Exception as e:
        print(f"Ошибка в reports: {e}")
        flash(f'Ошибка при генерации отчетов: {str(e)}', 'danger')
        return redirect(url_for('index'))
    
@app.route('/dwh_reports')
def dwh_reports():
    """Аналитические отчеты на основе DWH"""
    try:
        conn = get_dwh_connection()
        if conn is None:
            flash("Не удалось подключиться к хранилищу данных (DWH)", "danger")
            return redirect(url_for('index'))

        cur = conn.cursor()

        #  1. ТОП-10 товаров по суммарной стоимости 
        cur.execute("""
            SELECT dp.name, SUM(f.total_value) AS revenue
            FROM dwh.fact_inventory_movement f
            JOIN dwh.dim_product dp ON dp.product_key = f.product_key
            GROUP BY dp.name
            ORDER BY revenue DESC
            LIMIT 10;
        """)
        top_products = cur.fetchall()

        #  2. Активность складов 
        cur.execute("""
            SELECT dw.name, SUM(f.quantity) AS qty
            FROM dwh.fact_inventory_movement f
            JOIN dwh.dim_warehouse dw ON dw.warehouse_key = f.warehouse_key
            GROUP BY dw.name
            ORDER BY qty DESC;
        """)
        warehouse_activity = cur.fetchall()

        #  3. Динамика движений по датам 
        cur.execute("""
            SELECT dd.full_date, SUM(f.quantity)
            FROM dwh.fact_inventory_movement f
            JOIN dwh.dim_date dd ON dd.date_key = f.date_key
            GROUP BY dd.full_date
            ORDER BY dd.full_date;
        """)
        movement_trend = cur.fetchall()

        conn.close()

        return render_template(
            "dwh_reports.html",
            top_products=top_products,
            warehouse_activity=warehouse_activity,
            movement_trend=movement_trend
        )

    except Exception as e:
        print("Ошибка в DWH отчётах:", e)
        flash(f"Ошибка DWH: {str(e)}", "danger")
        return redirect(url_for("index"))



@app.route('/export')
def export_data():
    """Экспорт данных в CSV"""
    try:
        products = Product.query.all()
        
        data = []
        for product in products:
            data.append({
                'sku': product.sku,
                'name': product.name,
                'category': product.category,
                'unit_price': float(product.unit_price),
                'cost_price': float(product.cost_price),
                'quantity': product.quantity,
                'min_quantity': product.min_quantity,
                'max_quantity': product.max_quantity,
                'warehouse': product.warehouse.name if product.warehouse else '',
                'supplier': product.supplier.name if product.supplier else '',
                'total_value': product.total_value
            })
        
        df = pd.DataFrame(data)
        csv_data = df.to_csv(index=False, encoding='utf-8-sig')
        
        response = make_response(csv_data)
        response.headers['Content-Disposition'] = 'attachment; filename=warehouse_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
        
        return response
    except Exception as e:
        flash(f'Ошибка при экспорте: {str(e)}', 'danger')
        return redirect(url_for('products'))

@app.route('/search')
def search():
    """Поиск товаров"""
    try:
        query = request.args.get('q', '').strip()
        
        if not query:
            return redirect(url_for('products'))
        
        products = Product.query.filter(
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%'),
                Product.description.ilike(f'%{query}%')
            )
        ).limit(50).all()
        
        warehouses = Warehouse.query.filter(
            db.or_(
                Warehouse.name.ilike(f'%{query}%'),
                Warehouse.code.ilike(f'%{query}%'),
                Warehouse.location.ilike(f'%{query}%')
            )
        ).limit(10).all()
        
        suppliers = Supplier.query.filter(
            db.or_(
                Supplier.name.ilike(f'%{query}%'),
                Supplier.code.ilike(f'%{query}%'),
                Supplier.contact_person.ilike(f'%{query}%')
            )
        ).limit(10).all()
        
        return render_template('search.html',
                             query=query,
                             products=products,
                             warehouses=warehouses,
                             suppliers=suppliers)
    except Exception as e:
        flash(f'Ошибка поиска: {str(e)}', 'danger')
        return redirect(url_for('index'))


@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', 
                         error='Страница не найдена',
                         message='Запрошенная страница не существует.'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', 
                         error='Внутренняя ошибка сервера',
                         message='Произошла непредвиденная ошибка.'), 500


def init_test_data():
    """Инициализация тестовых данных"""
    with app.app_context():
        try:
            if Warehouse.query.count() == 0:
                print("Создаем тестовые данные...")
                
                # Склады
                warehouses = [
                    Warehouse(code='WH-001', name='Основной склад', 
                            location='Москва, ул. Промышленная, 1', max_capacity=10000),
                    Warehouse(code='WH-002', name='Холодильный склад',
                            location='Москва, ул. Холодильная, 15', max_capacity=5000),
                    Warehouse(code='WH-003', name='Региональный склад',
                            location='Санкт-Петербург, пр. Заводской, 45', max_capacity=8000)
                ]
                db.session.add_all(warehouses)
                db.session.flush()
                
                # Поставщики
                suppliers = [
                    Supplier(code='SUP-001', name='ТехноПоставка ООО', 
                            contact_person='Иванов Иван', phone='+7 (495) 123-45-67',
                            email='info@techno.ru', address='Москва, ул. Техническая, 12'),
                    Supplier(code='SUP-002', name='МебельМаркет',
                            contact_person='Петрова Мария', phone='+7 (495) 234-56-78',
                            email='sales@mebel.ru', address='Москва, ул. Мебельная, 34'),
                    Supplier(code='SUP-003', name='ПродуктТрейд',
                            contact_person='Сидоров Алексей', phone='+7 (495) 345-67-89',
                            email='office@product.ru', address='Москва, ул. Продуктовая, 56')
                ]
                db.session.add_all(suppliers)
                db.session.flush()
                
                # Товары
                products = [
                    Product(sku='NB-HP-001', name='Ноутбук HP ProBook', 
                          category='Электроника', unit_price=65000.00, cost_price=55000.00,
                          quantity=25, min_quantity=5, max_quantity=50,
                          warehouse_id=1, supplier_id=1),
                    Product(sku='MOUSE-001', name='Мышь беспроводная Logitech',
                          category='Электроника', unit_price=2500.00, cost_price=1800.00,
                          quantity=120, min_quantity=30, max_quantity=200,
                          warehouse_id=1, supplier_id=1),
                    Product(sku='CHAIR-001', name='Кресло офисное ERGO',
                          category='Мебель', unit_price=15000.00, cost_price=11000.00,
                          quantity=15, min_quantity=8, max_quantity=30,
                          warehouse_id=1, supplier_id=2),
                    Product(sku='TABLE-001', name='Стол письменный OfficePro',
                          category='Мебель', unit_price=22000.00, cost_price=17000.00,
                          quantity=8, min_quantity=5, max_quantity=20,
                          warehouse_id=1, supplier_id=2),
                ]
                db.session.add_all(products)
                
                db.session.commit()
                print("✅ Тестовые данные созданы!")
            else:
                print("✅ База данных уже содержит данные")
                
        except Exception as e:
            db.session.rollback()
            print(f"❌ Ошибка при создании тестовых данных: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    
    print("Создаем таблицы в PostgreSQL...")
    if create_tables():
        print("✅ Таблицы успешно созданы")
    else:
        print("❌ Не удалось создать таблицы")
    
    with app.app_context():
        try:
            db.create_all()
            print("✅ SQLAlchemy создал все таблицы")
        except Exception as e:
            print(f"❌ Ошибка SQLAlchemy при создании таблиц: {e}")
    
    init_test_data()
    
    print("🚀 Запуск приложения с PostgreSQL...")
    print("📊 Откройте в браузере: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)