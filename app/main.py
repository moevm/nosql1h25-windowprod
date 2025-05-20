from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import jwt
import bcrypt
from datetime import datetime, timedelta
import os
from typing import Optional, List, Dict
from arango.database import StandardDatabase
from arango.exceptions import ArangoError
from .db import db
from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from fastapi.responses import JSONResponse
from fastapi import File, UploadFile
import json
from io import BytesIO
from fastapi.responses import StreamingResponse
from pathlib import Path
import traceback



app = FastAPI(title="WindowShop", description="Система заказов оконных конструкций")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def format_datetime(value, format="%d.%m.%Y %H:%M:%S"):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime(format)

templates.env.filters["datetime"] = format_datetime

# Конфигурация JWT
SECRET_KEY = os.getenv("SECRET_KEY", "secret-key-123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class TokenData(BaseModel):
    username: str
    role: str
    exp: Optional[datetime] = None

class User(BaseModel):
    username: str
    role: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    id: Optional[str] = None

class ProductFilters(BaseModel):
    name: Optional[str] = None
    material: Optional[str] = None
    color: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_width: Optional[float] = None
    max_width: Optional[float] = None
    min_height: Optional[float] = None
    max_height: Optional[float] = None
    in_stock: Optional[bool] = None
    description : Optional[str] = None

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(request: Request) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None

    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            return None
        
        user_data = db.collection("users").find({"username": username}).next()
        return User(
            username=username,
            role=role,
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            id=user_data.get("_key")
        )
    except Exception as e:
        print(f"Ошибка декодирования токена: {e}")
        return None

def verify_role(user: User, allowed_roles: List[str]):
    if not user or user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для выполнения этого действия"
        )

def build_product_filters(filters: ProductFilters) -> dict:
    query_filters = {}
    
    # Текстовые фильтры (точное совпадение)
    if filters.name and filters.name.strip():
        query_filters["name"] = {"$like": f"%{filters.name}%"}  # Регистронезависимый поиск
    if filters.material and filters.material.strip():
        query_filters["material"] = filters.material
    if filters.color and filters.color.strip():
        query_filters["color"] = filters.color
    
    # Числовые фильтры (используем правильные операторы для ArangoDB)
    if filters.min_price is not None:
        query_filters["price"] = {">=": float(filters.min_price)}
    if filters.max_price is not None:
        if "price" in query_filters:
            query_filters["price"]["<="] = float(filters.max_price)
        else:
            query_filters["price"] = {"<=": float(filters.max_price)}
    
    # Фильтры по ширине
    if filters.min_width is not None:
        query_filters["width"] = {">=": float(filters.min_width)}
    if filters.max_width is not None:
        if "width" in query_filters:
            query_filters["width"]["<="] = float(filters.max_width)
        else:
            query_filters["width"] = {"<=": float(filters.max_width)}
    
    # Фильтры по высоте
    if filters.min_height is not None:
        query_filters["height"] = {">=": float(filters.min_height)}
    if filters.max_height is not None:
        if "height" in query_filters:
            query_filters["height"]["<="] = float(filters.max_height)
        else:
            query_filters["height"] = {"<=": float(filters.max_height)}
    
    # Фильтр по наличию
    if filters.in_stock is not None:
        query_filters["in_stock"] = bool(filters.in_stock)
    
    return query_filters

@app.get("/")
async def home(request: Request):
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/products")
    else:
        return RedirectResponse(url="/login")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None, "is_authenticated": False}
    )

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    try:
        user_data = db.collection("users").find({"username": username}).next()
        if not user_data or not bcrypt.checkpw(password.encode(), user_data["password_hash"].encode()):
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "error": "Неверный логин или пароль",
                    "is_authenticated": False
                },
                status_code=401
            )

        access_token = create_access_token(
            data={"sub": user_data["username"], "role": user_data["role"]},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            secure=False,
            samesite="lax"
        )
        return response
    except Exception as e:
        print(f"Ошибка входа: {e}")
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Ошибка сервера",
                "is_authenticated": False
            },
            status_code=500
        )

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("access_token")
    return response

@app.get("/products", response_class=HTMLResponse)
async def list_products(
        request: Request,
        user: User = Depends(get_current_user),
        name: Optional[str] = Query(None),
        material: Optional[str] = Query(None),
        color: Optional[str] = Query(None),
        description: Optional[str] = Query(None),
        min_price: Optional[str] = Query(None),
        max_price: Optional[str] = Query(None),
        min_width: Optional[str] = Query(None),
        max_width: Optional[str] = Query(None),
        min_height: Optional[str] = Query(None),
        max_height: Optional[str] = Query(None),
        in_stock: Optional[str] = Query(None)
):
    try:
        def parse_float(value: Optional[str]) -> Optional[float]:
            try:
                if value and value.strip():
                    return float(value.strip())
                return None
            except ValueError:
                return None

        # Преобразуем параметры запроса в фильтры
        filters = ProductFilters(
            name=name,
            description=description,
            material=material,
            color=color,
            min_price=parse_float(min_price),
            max_price=parse_float(max_price),
            min_width=parse_float(min_width),
            max_width=parse_float(max_width),
            min_height=parse_float(min_height),
            max_height=parse_float(max_height),
            in_stock=in_stock == 'on' if in_stock is not None else None
        )

        # Формируем AQL запрос
        aql_query = "FOR p IN products"
        bind_vars = {}
        filter_conditions = []

        # Улучшенный поиск по подстроке для текстовых полей
        if filters.name:
            filter_conditions.append("LIKE(LOWER(p.name), CONCAT('%', LOWER(@name), '%'))")
            bind_vars["name"] = filters.name.strip().lower()

        if filters.material:
            filter_conditions.append("LIKE(LOWER(p.material), CONCAT('%', LOWER(@material), '%'))")
            bind_vars["material"] = filters.material.strip().lower()

        if filters.color:
            filter_conditions.append("LIKE(LOWER(p.color), CONCAT('%', LOWER(@color), '%'))")
            bind_vars["color"] = filters.color.strip().lower()

        if filters.min_price is not None:
            filter_conditions.append("p.price >= @min_price")
            bind_vars["min_price"] = float(filters.min_price)

        if filters.max_price is not None:
            filter_conditions.append("p.price <= @max_price")
            bind_vars["max_price"] = float(filters.max_price)

        if filters.min_width is not None:
            filter_conditions.append("p.width >= @min_width")
            bind_vars["min_width"] = float(filters.min_width)

        if filters.max_width is not None:
            filter_conditions.append("p.width <= @max_width")
            bind_vars["max_width"] = float(filters.max_width)

        if filters.min_height is not None:
            filter_conditions.append("p.height >= @min_height")
            bind_vars["min_height"] = float(filters.min_height)

        if filters.max_height is not None:
            filter_conditions.append("p.height <= @max_height")
            bind_vars["max_height"] = float(filters.max_height)

        if filters.description:
            filter_conditions.append("LIKE(LOWER(p.description), CONCAT('%', LOWER(@description), '%'))")
            bind_vars["description"] = filters.description.strip().lower()

        if filters.in_stock is not None:
            filter_conditions.append("p.in_stock == @in_stock")
            bind_vars["in_stock"] = bool(filters.in_stock)

        if filter_conditions:
            aql_query += " FILTER " + " AND ".join(filter_conditions)

        aql_query += " RETURN p"

        # Выполняем запрос
        products = list(db.aql.execute(aql_query, bind_vars=bind_vars))

        # Подготавливаем данные для шаблона
        template_data = {
            "request": request,
            "user": user,
            "products": products,
            "is_authenticated": user is not None,
            "filters": {
                "name": name or "",
                "description": description or "",
                "material": material or "",
                "color": color or "",
                "min_price": min_price or "",
                "max_price": max_price or "",
                "min_width": min_width or "",
                "max_width": max_width or "",
                "min_height": min_height or "",
                "max_height": max_height or "",
                "in_stock": in_stock == 'on' if in_stock is not None else False
            }
        }

        return templates.TemplateResponse("products/list.html", template_data)

    except Exception as e:
        print(f"Ошибка при загрузке товаров: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Ошибка загрузки каталога"},
            status_code=500
        )


@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    
    try:
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": user,
                "is_authenticated": True
            }
        )
    except Exception as e:
        print(f"Ошибка загрузки профиля: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Ошибка загрузки профиля"},
            status_code=500
        )

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["admin", "superadmin"])
    
    try:
        stats = {
            "products_count": db.collection("products").count(),
            "orders_count": db.collection("orders").count(),
            "users_count": db.collection("users").count()
        }
        return templates.TemplateResponse(
            "admin/dashboard.html",
            {
                "request": request,
                "user": user,
                "is_authenticated": True,
                "stats": stats
            }
        )
    except Exception as e:
        print(f"Ошибка загрузки админ-панели: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Ошибка загрузки админ-панели"},
            status_code=500
        )

@app.get("/order/new", response_class=HTMLResponse)
async def new_order_form(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["customer"])
    try:
        products = list(db.collection("products").find({"in_stock": True}))
        return templates.TemplateResponse(
            "orders/new.html",
            {
                "request": request,
                "user": user,
                "products": products,
                "is_authenticated": True
            }
        )
    except Exception as e:
        print(f"Ошибка загрузки формы заказа: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Ошибка загрузки формы заказа"},
            status_code=500
        )

@app.post("/order/create")
async def create_order(
    request: Request,
    user: User = Depends(get_current_user),
    product_id: str = Form(...),
    quantity: int = Form(1),
    address: str = Form(...),
    comments: str = Form(None)
):
    verify_role(user, ["customer"])
    try:
        # Получаем информацию о продукте
        product = db.collection("products").get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Товар не найден")

        # Создаем заказ
        order_data = {
            "customer_id": user.id,
            "customer_name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
            "product_id": product_id,
            "product_name": product["name"],
            "quantity": quantity,
            "address": address,
            "comments": comments,
            "status": "new",
            "total_price": product["price"] * quantity,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        # Сохраняем заказ в БД
        order = db.collection("orders").insert(order_data)

        # Проверяем и создаем коллекцию user_orders, если она не существует
        if not db.has_collection("user_orders"):
            db.create_collection("user_orders", edge=True)
            print("Создана edge-коллекция user_orders")

        # Создаем связь между пользователем и заказом
        db.collection("user_orders").insert({
            "_from": f"users/{user.id}",
            "_to": f"orders/{order['_key']}",
            "type": "created",
            "created_at": datetime.utcnow().isoformat()
        })

        return RedirectResponse(url="/my-orders", status_code=303)

    except ArangoError as e:
        print(f"Ошибка базы данных при создании заказа: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Ошибка базы данных при создании заказа"},
            status_code=500
        )
    except Exception as e:
        print(f"Ошибка создания заказа: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Ошибка создания заказа"},
            status_code=500
        )

@app.get("/my-orders", response_class=HTMLResponse)
async def my_orders(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["customer"])
    try:
        # Получаем заказы пользователя через AQL запрос
        query = """
        FOR order IN orders
        FILTER order.customer_id == @customer_id
        SORT order.created_at DESC
        RETURN {
            id: order._key,
            product_name: order.product_name,
            quantity: order.quantity,
            address: order.address,
            status: order.status,
            total_price: order.total_price,
            created_at: order.created_at,
            comments: order.comments
        }
        """
        orders = list(db.aql.execute(query, bind_vars={"customer_id": user.id}))
        
        return templates.TemplateResponse(
            "orders/my_orders.html",
            {
                "request": request,
                "user": user,
                "orders": orders,
                "is_authenticated": True
            }
        )
    except ArangoError as e:
        print(f"Ошибка базы данных при загрузке заказов: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Ошибка загрузки ваших заказов"},
            status_code=500
        )
    except Exception as e:
        print(f"Ошибка загрузки заказов: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Ошибка загрузки ваших заказов"},
            status_code=500
        )

@app.get("/api/health")
async def health_check():
    try:
        return {
            "status": "OK",
            "db_initialized": bool(db),
            "users_count": db.collection("users").count() if db and db.has_collection("users") else 0,
            "products_count": db.collection("products").count() if db and db.has_collection("products") else 0,
            "orders_count": db.collection("orders").count() if db and db.has_collection("orders") else 0
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e)
        }
    

# Для пользователей
@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["admin", "superadmin"])
    users = list(db.collection("users").find({}))
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": users,
            "user": user,
            "is_authenticated": True
        }
    )
    
# Маршруты для управления товарами
@app.get("/admin/products/new", response_class=HTMLResponse)
async def new_product_form(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["admin", "superadmin"])
    return templates.TemplateResponse(
        "admin/new_product.html",
        {"request": request, "user": user, "is_authenticated": True}
    )

@app.post("/admin/products/new")
async def create_product(
        request: Request,
        user: User = Depends(get_current_user),
        name: str = Form(...),
        description: str = Form(...),
        price: float = Form(...),
        width: float = Form(...),
        height: float = Form(...),
        material: str = Form(...),
        color: str = Form("белый"),
        in_stock: str = Form("on")
):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    verify_role(user, ["admin", "superadmin"])

    errors = {}


    if not name.strip():
        errors["name"] = "Название не может быть пустым"
    if price <= 0:
        errors["price"] = "Цена должна быть больше нуля"
    if width <= 0:
        errors["width"] = "Ширина должна быть больше нуля"
    if height <= 0:
        errors["height"] = "Высота должна быть больше нуля"


    if errors:
        return templates.TemplateResponse(
            "admin/new_product.html",
            {
                "request": request,
                "user": user,
                "is_authenticated": True,
                "errors": errors,
                "form_data": {
                    "name": name,
                    "description": description,
                    "price": price,
                    "width": width,
                    "height": height,
                    "material": material,
                    "color": color,
                    "in_stock": in_stock
                }
            },
            status_code=400
        )

    product_data = {
        "name": name.strip(),
        "description": description.strip(),
        "price": float(price),
        "width": float(width),
        "height": float(height),
        "material": material.strip(),
        "color": color.strip(),
        "in_stock": in_stock.lower() == "on",
        "created_at": datetime.utcnow().isoformat()
    }

    db.collection("products").insert(product_data)
    return RedirectResponse(url="/admin/products", status_code=303)

# Для товаров
@app.get("/admin/products", response_class=HTMLResponse)
async def admin_products(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["admin", "superadmin"])
    products = list(db.collection("products").find({}))
    return templates.TemplateResponse(
        "admin/products.html",
        {
            "request": request,
            "products": products,
            "user": user,
            "is_authenticated": True
        }
    )
    

# Маршруты для управления заказами
@app.get("/admin/orders/new", response_class=HTMLResponse)
async def new_order_form(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["admin", "superadmin"])
    products = list(db.collection("products").find({"in_stock": True}))
    customers = list(db.collection("users").find({"role": "customer"}))
    return templates.TemplateResponse(
        "admin/new_order.html",
        {
            "request": request,
            "products": products,
            "customers": customers,
            "user": user,
            "is_authenticated": True
        }
    )


# Для заказов
@app.get("/admin/orders", response_class=HTMLResponse)
async def admin_orders(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["admin", "superadmin"])
    orders = list(db.collection("orders").find({}))
    return templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "orders": orders,
            "user": user,
            "is_authenticated": True
        }
    )
# Маршруты для управления пользователями
@app.get("/admin/users/new", response_class=HTMLResponse)
async def new_user_form(request: Request, user: User = Depends(get_current_user)):
    verify_role(user, ["superadmin"])  # Только superadmin может добавлять пользователей
    return templates.TemplateResponse(
        "admin/new_user.html",
        {"request": request, "user": user, "is_authenticated": True}
    )

@app.post("/admin/users/{user_key}/change-role")
async def change_user_role(
        request: Request,
        user_key: str,
        current_user: User = Depends(get_current_user)
):
    verify_role(current_user, ["superadmin"])

    if current_user.id == user_key:
        raise HTTPException(
            status_code=400,
            detail="Нельзя изменить свою собственную роль"
        )

    data = await request.json()
    new_role = data.get("new_role")

    if not new_role:
        raise HTTPException(
            status_code=400,
            detail="Не указана новая роль"
        )

    allowed_roles = ["customer", "measurer", "admin", "superadmin"]
    if new_role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail="Недопустимая роль пользователя"
        )

    try:
        user = db.collection("users").get(f"users/{user_key}")
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        db.collection("users").update_match({"_key": user_key}, {"role": new_role})
        return {"status": "ok", "new_role": new_role}

    except ArangoError as e:
        print(f"Ошибка обновления роли: {e}")
        raise HTTPException(
            status_code=500,
            detail="Ошибка при обновлении роли пользователя"
        )


@app.get("/admin/export")
async def export_data(user: User = Depends(get_current_user)):
    verify_role(user, ["admin", "superadmin"])

    try:
        # Собираем все данные
        data = {
            "products": list(db.collection("products").all()),
            "orders": list(db.collection("orders").all()),
            "users": list(db.collection("users").all()),
            "measurements": list(db.collection("measurements").all()),
        }

        # Преобразуем в JSON
        json_data = json.dumps(data, ensure_ascii=False, indent=2)

        # Создаем поток для ответа
        buffer = BytesIO()
        buffer.write(json_data.encode("utf-8"))
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=export.json"
            }
        )
    except Exception as e:
        print(f"Ошибка экспорта: {e}")
        raise HTTPException(status_code=500, detail="Ошибка экспорта данных")
@app.post("/admin/import")
async def import_all_data(
    user: User = Depends(get_current_user),
    file: UploadFile = File(...)
):
    verify_role(user, ["admin", "superadmin"])

    try:
        content = await file.read()
        data = json.loads(content)

        # Импортируем каждый тип данных
        for collection_name in ["products", "orders", "users"]:
            if collection_name in data:
                for item in data[collection_name]:
                    db.collection(collection_name).insert(item, overwrite=True)

        return RedirectResponse("/admin/dashboard", status_code=303)
    except Exception as e:
        print(f"Ошибка импорта данных: {e}")
        raise HTTPException(status_code=400, detail="Ошибка импорта данных")

async def parse_form_data(request: Request):
    form = await request.form()
    return dict(form)


@app.get("/entities/{entity_type}/", response_class=HTMLResponse)
async def list_entities(request: Request, entity_type: str, user: User = Depends(get_current_user)):
    if not user:
        print("Redirecting to /login — user is None")
        return RedirectResponse("/login")
    print(f"User role: {user.role}")
    verify_role(user, ["superadmin"])

    # Проверяем, что entity_type поддерживается
    allowed = ["users", "products", "orders", "measurements", "photos"]
    if entity_type not in allowed:
        return HTMLResponse("Entity type not supported", status_code=400)

    collection = db.collection(entity_type)
    entities = list(collection.all())

    return templates.TemplateResponse(
        "entities/list.html",
        {"request": request, "entities": entities, "entity_type": entity_type, "user": user , "is_authenticated": True}
    )
@app.get("/entities/{entity_type}/{entity_id}/edit", response_class=HTMLResponse)
async def edit_entity_form(request: Request, entity_type: str, entity_id: str, user: User = Depends(get_current_user)):
    if not user:
        print("Redirecting to /login — user is None")
        return RedirectResponse("/login")
    print(f"User role: {user.role}")
    verify_role(user, ["superadmin"])
    collection = db.collection(entity_type)
    entity = collection.get(entity_id)
    return templates.TemplateResponse("entities/edit.html", {"request": request, "entity": entity, "entity_type": entity_type , "user": user ,"is_authenticated": True})


@app.post("/entities/{entity_type}/{item_id}/edit")
async def entity_edit(request: Request, entity_type: str, item_id: str, user: User = Depends(get_current_user)):
    if not user:
        print("Redirecting to /login — user is None")
        return RedirectResponse("/login")
    print(f"User role: {user.role}")

    verify_role(user, ["superadmin"])

    form = await request.form()
    data = dict(form)

    if entity_type not in ["users", "products", "orders", "measurements",  "photos"]:
        return HTMLResponse("Тип сущности не найден", status_code=404)

    db.collection(entity_type).update_match({"_key": item_id}, data)

    return RedirectResponse(url=f"/entities/{entity_type}/", status_code=303)


@app.get("/entities/", response_class=HTMLResponse)
async def choose_entity_type(request: Request, user: User = Depends(get_current_user)):
    if not user:
        print("Redirecting to /login — user is None")
        return RedirectResponse("/login")
    print(f"User role: {user.role}")
    verify_role(user, ["superadmin"])
    entity_types = ["users", "products", "orders", "measurements",  "photos"]
    return templates.TemplateResponse("entities/choose_type.html", {"request": request, "entity_types": entity_types, "user": user, "is_authenticated": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
