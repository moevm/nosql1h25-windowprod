from arango import ArangoClient
from arango.exceptions import ArangoServerError, CollectionCreateError
import os
from typing import Optional
from arango.database import StandardDatabase
from datetime import datetime
from arango.exceptions import ArangoServerError, CollectionCreateError
import bcrypt

# Конфигурация подключения к ArangoDB
ARANGO_HOST = os.getenv("ARANGO_HOST", "http://arangodb:8529")
DB_NAME = os.getenv("ARANGO_DB", "windowshop")
DB_USER = os.getenv("ARANGO_USER", "root")
DB_PASS = os.getenv("ARANGO_PASS", "openSesame")

# Глобальная переменная для хранения подключения
_db: Optional['StandardDatabase'] = None

def get_db():
    """Устанавливает соединение с ArangoDB и возвращает объект базы данных"""
    global _db
    if _db is None:
        try:
            client = ArangoClient(hosts=ARANGO_HOST)
            sys_db = client.db('_system', username=DB_USER, password=DB_PASS)
            
            if not sys_db.has_database(DB_NAME):
                sys_db.create_database(DB_NAME)
                print(f"Создана база данных: {DB_NAME}")
            
            _db = client.db(DB_NAME, username=DB_USER, password=DB_PASS)
        except Exception as e:
            print(f"Ошибка подключения к ArangoDB: {e}")
            raise
    return _db

def init_db():
    """Инициализирует базу данных: создает коллекции, индексы и тестовые данные"""
    try:
        db = get_db()
        
        # Создаем основные коллекции
        collections = [
            "users",       # Пользователи системы
            "products",    # Окна
            "orders",      # Заказы клиентов
            "measurements", # Замеры
            "payments",     # Платежи
            "photos"        # Фотографии товаров
        ]
        
        # Создаем edge-коллекции для связей
        edge_collections = [
            ("created_order", "users", "orders"),      # Пользователь создал заказ
            ("contain_product", "orders", "products"), # Заказ содержит товары
            ("product_photos", "products", "photos"),  # Товар имеет фотографии
            ("assigned_measurement", "users", "measurements") # Замерщик назначен на замер
        ]
        
        # Создаем обычные коллекции
        for col_name in collections:
            if not db.has_collection(col_name):
                db.create_collection(col_name)
                print(f"Создана коллекция: {col_name}")

        # Создаем edge-коллекции и связи
        for edge_name, from_col, to_col in edge_collections:
            if not db.has_collection(edge_name):
                db.create_collection(edge_name, edge=True)
                print(f"Создана edge-коллекция: {edge_name} ({from_col} -> {to_col})")
        
        # Создаем индексы для ускорения поиска
        if db.has_collection("users"):
            users = db.collection("users")
            users.add_persistent_index(["phone_number"], unique=True)
            users.add_persistent_index(["role"])
            users.add_persistent_index(["last_name", "first_name"])
        
        if db.has_collection("products"):
            products = db.collection("products")
            products.add_persistent_index(["name"])
            products.add_persistent_index(["material"])
            products.add_persistent_index(["price"])
            products.add_fulltext_index(["description"])
        
        # Инициализация тестовых данных
        init_test_data(db)
        
        return db
    except Exception as e:
        print(f"Ошибка инициализации БД: {e}")
        raise

def init_test_data(db):
    """Заполняет базу тестовыми данными"""
    # Тестовые пользователи для всех ролей
    if db.collection("users").count() == 0:
        users_data = [
            # SuperAdmin (полные права)
            {
                "_key": "superadmin",
                "username": "superadmin",
                "password_hash": bcrypt.hashpw(b"superadmin123", bcrypt.gensalt()).decode(),
                "role": "superadmin",
                "first_name": "Алексей",
                "last_name": "Главный",
                "phone_number": "+79110000000",
                "birth_date": "1980-01-01",
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True
            },
            # Администратор
            {
                "_key": "admin",
                "username": "admin",
                "password_hash": bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode(),
                "role": "admin",
                "first_name": "Ольга",
                "last_name": "Администраторова",
                "phone_number": "+79110000001",
                "birth_date": "1985-05-15",
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True
            },
            # Замерщик
            {
                "_key": "measurer1",
                "username": "measurer1",
                "password_hash": bcrypt.hashpw(b"measurer123", bcrypt.gensalt()).decode(),
                "role": "measurer",
                "first_name": "Иван",
                "last_name": "Замеров",
                "phone_number": "+79110000002",
                "birth_date": "1990-07-20",
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True
            },
            {
                "_key": "customer1",
                "username": "customer1",
                "password_hash": bcrypt.hashpw(b"customer123", bcrypt.gensalt()).decode(),
                "role": "customer",
                "first_name": "Елена",
                "last_name": "Покупателева",
                "phone_number": "+79110000003",
                "birth_date": "1995-11-30",
                "created_at": datetime.utcnow().isoformat(),
                "is_active": True
            }
        ]
        db.collection("users").import_bulk(users_data)
        print("Добавлены тестовые пользователи")

    # Тестовые товары (оконные конструкции)
    if db.collection("products").count() == 0:
        products_data = [
            {
                "_key": "prod1",
                "name": "Окно ПВХ Стандарт",
                "description": "Одностворчатое окно из белого ПВХ профиля",
                "height": 1.5,
                "width": 1.2,
                "material": "ПВХ",
                "color": "белый",
                "equipment": "Стандарт",
                "sum_of_sections": 1,
                "price": 12500,
                "in_stock": True,
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "_key": "prod2",
                "name": "Окно ПВХ Премиум",
                "description": "Двухстворчатое окно с энергосберегающим стеклопакетом",
                "height": 1.8,
                "width": 1.5,
                "material": "ПВХ",
                "color": "коричневый",
                "equipment": "Премиум",
                "sum_of_sections": 2,
                "price": 21500,
                "in_stock": True,
                "created_at": datetime.utcnow().isoformat()
            }
        ]
        db.collection("products").import_bulk(products_data)
        print("Добавлены тестовые товары")

    # Создаем тестовые заказы
    if db.collection("orders").count() == 0 and db.collection("users").count() > 0:
        orders_data = [
            {
                "_key": "order1",
                "address": "г. Москва, ул. Ленина, д. 10, кв. 5",
                "email": "client1@example.com",
                "status": "new",
                "comments": "Подъезд со двора",
                "sum_price": 12500,
                "created_at": datetime.utcnow().isoformat()
            }
        ]
        db.collection("orders").import_bulk(orders_data)
