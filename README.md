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

## 🚂 Despliegue en Railway

El backend está listo para Railway (Nixpacks + Procfile + railway.json).

1. En [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo** → elige `axis-pos`.
2. En el servicio, **Settings → Root Directory** = `backend`.
3. **Add Plugin → PostgreSQL** (y opcional **Redis** para WebSockets en producción).
   Railway inyecta `DATABASE_URL` y `REDIS_URL` automáticamente.
4. **Variables** del servicio:
   ```
   SECRET_KEY=<genera-uno-seguro>
   DEBUG=False
   CORS_ALLOWED_ORIGINS=https://tu-frontend.vercel.app
   ```
   (`RAILWAY_PUBLIC_DOMAIN` ya lo inyecta Railway y se agrega a ALLOWED_HOSTS.)
5. Deploy. El `preDeployCommand` corre `migrate` + `collectstatic`; el servicio
   arranca con Daphne (HTTP + WebSocket) en `$PORT`.
6. Carga datos demo desde la consola del servicio:
   ```
   python manage.py seed
   ```
   Crea un **usuario para iniciar sesión** y el restaurante demo:
   - Usuario: `admin@axispos.co`
   - Contraseña: `Axis2026!`  ← cámbiala en producción

   (Usa `python manage.py createsuperuser` si quieres otro admin.)

> Sin Postgres usa SQLite y sin Redis usa una capa de canales en memoria, así el
> servicio **arranca aunque aún no agregues plugins**. Para producción real añade
> ambos. Las migraciones (`api/migrations/0001_initial.py`) ya están incluidas, así
> que el deploy crea las tablas sin pasos manuales.

## Conectar el frontend (Vercel)
En el proyecto Next.js define las variables y redeploy:
```
NEXT_PUBLIC_USE_API=true
NEXT_PUBLIC_API_URL=https://<tu-backend>.railway.app/api/v1
NEXT_PUBLIC_WS_URL=wss://<tu-backend>.railway.app
```
