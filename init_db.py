import sqlite3

conn = sqlite3.connect('store.db')
cursor = conn.cursor()

# Таблица товаров
cursor.execute('''
CREATE TABLE IF NOT EXISTS products(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price INTEGER NOT NULL,
    description TEXT,
    image_url TEXT,
    category TEXT
)
''')

# Таблица заказов
cursor.execute('''
CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    user_name TEXT,
    phone TEXT,
    address TEXT,
    order_details TEXT,
    total_price INTEGER,
    order_date TEXT,
    status TEXT
)
''')

# Таблица пользователей (с tg_id!)
cursor.execute('''
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER UNIQUE,
    name TEXT,
    phone TEXT,
    address TEXT
)
''')

products = [
    ("Смартфон X123", 29990, "Современный смартфон с отличной камерой", None, "Электроника"),
    ("Наушники Y456", 4990, "Беспроводные наушники с шумоподавлением", None, "Электроника"),
    ("Футболка Z789", 990, "Хлопковая футболка с принтом", None, "Одежда"),
    ("Куртка Winter", 4990, "Тёплая зимняя куртка", None, "Одежда")
]

cursor.executemany('INSERT INTO products (name, price, description, image_url, category) VALUES (?, ?, ?, ?, ?)', products)

conn.commit()
conn.close()
print("База данных успешно инициализирована.")
