# Axis POS — Backend (Django + DRF + Channels)

Backend multi-tenant para Axis POS. Expone la API REST que el frontend ya
consume (mismos paths y JSON) y los WebSockets para el KDS en tiempo real.

## Stack
- **Django 5 + Django REST Framework** — API REST
- **Channels + Redis** — WebSockets (KDS de cocina, pedidos web)
- **PostgreSQL** — base de datos
- **Celery + Redis** — tareas async (facturación, sincronización)
- **SimpleJWT** — autenticación por token

## Puesta en marcha
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # configura DATABASE_URL y REDIS_URL
python manage.py migrate
python manage.py createsuperuser
# Servidor ASGI (HTTP + WebSocket) con Daphne
python manage.py runserver      # dev
# o producción: daphne -b 0.0.0.0 -p 8000 config.asgi:application
# Tareas async:
celery -A config worker -l info
```

## Mapa API ↔ Frontend
Cada servicio del frontend (`src/services/*.service.ts`) apunta a estos endpoints:

| Frontend service        | Endpoint DRF                          |
|-------------------------|---------------------------------------|
| `menu.service`          | `GET /api/v1/menu/categories/` · `/menu/products/` |
| `inventory.service`     | `GET /api/v1/inventory/` · `/inventory/movements/` |
| `salon.service`         | `GET /api/v1/tables/`                 |
| `recipes.service`       | CRUD `/api/v1/recipes/`               |
| `crm.service`           | CRUD `/api/v1/customers/`             |
| `orders.service`        | CRUD `/api/v1/orders/`                |
| auth                    | `POST /api/v1/auth/token/`            |
| KDS realtime            | `ws://…/ws/kitchen/<tenant>/`         |

## Conectar el frontend
En el frontend, define en `.env.local`:
```
NEXT_PUBLIC_USE_API=true
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```
y en cada `*.service.ts` cambia `mockRequest(DATA)` por `request<T>("/endpoint/")`
(la función `request` ya está implementada en `src/services/http.ts`).

> Scaffold listo para evolucionar. Faltan migraciones generadas, seeds y tests
> del backend; la estructura y los contratos ya coinciden con la UI.
