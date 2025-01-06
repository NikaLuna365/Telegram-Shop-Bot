import sqlite3
from datetime import datetime

DB_PATH = 'store.db'

def get_categories():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category FROM products")
    categories = [row[0] for row in cursor.fetchall()]
    conn.close()
    return categories

def get_products_by_category(category):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, description, image_url FROM products WHERE category = ?", (category,))
    products = cursor.fetchall()
    conn.close()
    return products

def get_product_by_id(product_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, description, image_url, category FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()
    return product

def save_order(user_id, user_name, phone, address, order_details, total_price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    order_date = datetime.now().strftime("%d.%m.%Y %H:%M")
    cursor.execute('''
    INSERT INTO orders (user_id, user_name, phone, address, order_details, total_price, order_date, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, user_name, phone, address, order_details, total_price, order_date, "Новый"))
    conn.commit()
    order_id = cursor.lastrowid
    conn.close()
    return order_id

def get_user_data(tg_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Используем tg_id для выборки пользователя
    cursor.execute("SELECT id, name, phone, address FROM users WHERE tg_id = ?", (tg_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def save_user_data(tg_id, name, phone, address):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    existing = get_user_data(tg_id)
    if existing:
        cursor.execute("UPDATE users SET name=?, phone=?, address=? WHERE tg_id=?", (name, phone, address, tg_id))
    else:
        cursor.execute("INSERT INTO users (tg_id, name, phone, address) VALUES (?, ?, ?, ?)", (tg_id, name, phone, address))
    conn.commit()
    conn.close()

def get_user_id_by_tg(tg_id):
    user = get_user_data(tg_id)
    if user:
        return user[0]
    return None

def get_orders_by_user(tg_id, limit=5):
    user_id = get_user_id_by_tg(tg_id)
    if not user_id:
        return []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT order_date, order_details, total_price FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    orders = cursor.fetchall()
    conn.close()
    return orders

def update_order_status(order_id, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()

def add_product(name, price, description, category, image_url=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO products (name, price, description, image_url, category) VALUES (?, ?, ?, ?, ?)",
                   (name, price, description, image_url, category))
    conn.commit()
    conn.close()
