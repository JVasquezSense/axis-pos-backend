"""
ViewSets DRF. Cada uno filtra por el tenant del usuario autenticado
(aislamiento multi-tenant) y mapea a los endpoints que el frontend ya llama.
"""
from rest_framework import viewsets, decorators, response, status, views as drf_views, permissions
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate, ExtractHour
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from . import models, serializers


def resolve_tenant_id(user):
    """
    Resuelve el tenant del usuario autenticado desde su UserProfile.
    Fail-closed: en un entorno multi-tenant devuelve None si no se puede
    resolver (para no exponer datos de otro restaurante). En un despliegue
    con un único Tenant asume ese tenant.
    """
    if user is not None and getattr(user, "is_authenticated", False):
        tenant_id = getattr(user, "tenant_id", None)
        if not tenant_id:
            try:
                tenant_id = user.profile.tenant_id
            except Exception:
                tenant_id = None
        if tenant_id:
            return tenant_id
    if models.Tenant.objects.count() == 1:
        first = models.Tenant.objects.first()
        return first.pk if first else None
    return None


class TenantQuerySet:
    """
    Mixin: limita el queryset al restaurante del usuario autenticado.

    Aislamiento fail-closed: el tenant se resuelve EXCLUSIVAMENTE desde el
    usuario autenticado (su UserProfile). Si no se puede resolver, el queryset
    queda vacío en lugar de exponer datos de otro restaurante.

    Excepción controlada: en un despliegue con un único Tenant se asume ese
    tenant (setup single-tenant / webhooks internos), porque no hay datos de
    terceros que filtrar. Con varios tenants NUNCA se adivina.
    """
    def _resolve_tenant_id(self):
        return resolve_tenant_id(getattr(self.request, "user", None))

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = self._resolve_tenant_id()
        return qs.filter(tenant_id=tenant_id) if tenant_id else qs.none()

    def perform_create(self, serializer):
        tenant_id = self._resolve_tenant_id()
        if not tenant_id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("No se pudo resolver el restaurante del usuario.")
        serializer.save(tenant_id=tenant_id)


class CategoryViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer


class ProductViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Product.objects.select_related("category")
    serializer_class = serializers.ProductSerializer


class InventoryViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.InventoryItem.objects.all()
    serializer_class = serializers.InventoryItemSerializer

    @decorators.action(detail=False, methods=["get"])
    def movements(self, request):
        tenant_id = resolve_tenant_id(request.user)
        qs = models.InventoryMovement.objects.filter(item__tenant_id=tenant_id) if tenant_id \
            else models.InventoryMovement.objects.none()
        return response.Response(serializers.InventoryMovementSerializer(qs, many=True).data)

    @decorators.action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        """Ajuste manual de stock desde el frontend (post-venta)."""
        item = self.get_object()
        new_stock = request.data.get("stock")
        reason = request.data.get("reason", "Ajuste manual")
        if new_stock is None:
            return response.Response({"error": "stock requerido"}, status=status.HTTP_400_BAD_REQUEST)
        old_stock = float(item.stock)
        item.stock = float(new_stock)
        item.recompute_status()
        item.save()
        delta = float(new_stock) - old_stock
        models.InventoryMovement.objects.create(
            tenant=item.tenant,
            item=item,
            type="salida" if delta < 0 else "ajuste",
            quantity=delta,
            balance=item.stock,
            unit_cost=item.cost,
            reason=reason,
        )
        return response.Response(serializers.InventoryItemSerializer(item).data)


class TableViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Table.objects.all()
    serializer_class = serializers.TableSerializer


class RecipeViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Recipe.objects.prefetch_related("ingredients")
    serializer_class = serializers.RecipeSerializer


class CustomerViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Customer.objects.all()
    serializer_class = serializers.CustomerSerializer


class OrderViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Order.objects.prefetch_related("lines").order_by("-created_at")
    serializer_class = serializers.OrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get("status")
        if status_param:
            statuses = [s.strip() for s in status_param.split(",") if s.strip()]
            qs = qs.filter(status__in=statuses)
        table_param = self.request.query_params.get("table")
        if table_param:
            qs = qs.filter(table__number=table_param)
        return qs

    def perform_create(self, serializer):
        tenant_id = self._resolve_tenant_id()
        order = serializer.save(tenant_id=tenant_id) if tenant_id else serializer.save()
        # Empuja ticket a cocina vía WebSocket
        try:
            layer = get_channel_layer()
            async_to_sync(layer.group_send)(
                f"kitchen_{order.tenant_id}",
                {"type": "ticket.new", "ticket": serializers.OrderSerializer(order).data},
            )
        except Exception:
            pass

    def perform_update(self, serializer):
        order = serializer.save()
        # Avisa cambios de estado (ej. preparando/listo) a otras pantallas conectadas
        try:
            layer = get_channel_layer()
            async_to_sync(layer.group_send)(
                f"kitchen_{order.tenant_id}",
                {"type": "ticket.update", "payload": serializers.OrderSerializer(order).data},
            )
        except Exception:
            pass


# ─── Proveedores ──────────────────────────────────────────────────────────────

class SupplierViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Supplier.objects.all()
    serializer_class = serializers.SupplierSerializer


class PurchaseViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Purchase.objects.prefetch_related("lines__inventory_item").select_related("supplier")
    serializer_class = serializers.PurchaseSerializer


# ─── Reservaciones ───────────────────────────────────────────────────────────

class ReservationViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Reservation.objects.all().order_by("date", "time")
    serializer_class = serializers.ReservationSerializer


# ─── Empleados ───────────────────────────────────────────────────────────────

class EmployeeViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Employee.objects.all().order_by("name")
    serializer_class = serializers.EmployeeSerializer


# ─── Ventas ──────────────────────────────────────────────────────────────────

# ─── Super Admin ─────────────────────────────────────────────────────────────

class AdminTenantViewSet(viewsets.ModelViewSet):
    """CRUD completo de tenants. Solo superadmin debe acceder."""
    queryset = models.Tenant.objects.all().order_by("-created_at")
    serializer_class = serializers.TenantAdminSerializer
    permission_classes = [permissions.IsAdminUser]

    @decorators.action(detail=True, methods=["patch"], url_path="features")
    def update_features(self, request, pk=None):
        tenant = self.get_object()
        features = request.data.get("features")
        if not isinstance(features, dict):
            return response.Response({"error": "features must be a dict"}, status=status.HTTP_400_BAD_REQUEST)
        tenant.features = {**tenant.features, **features}
        tenant.save(update_fields=["features"])
        return response.Response(serializers.TenantAdminSerializer(tenant).data)

    @decorators.action(detail=True, methods=["get", "post"], url_path="users", url_name="users")
    def users(self, request, pk=None):
        tenant = self.get_object()
        if request.method == "GET":
            qs = models.UserProfile.objects.filter(tenant=tenant).select_related("user")
            users = [p.user for p in qs]
            return response.Response(serializers.TenantUserSerializer(users, many=True).data)
        # POST — crear usuario
        from django.contrib.auth import get_user_model
        User = get_user_model()
        username = request.data.get("username", "").strip()
        email = request.data.get("email", "").strip()
        password = request.data.get("password", "")
        role = request.data.get("role", "admin")
        if not email or not password:
            return response.Response({"error": "email y password requeridos"}, status=status.HTTP_400_BAD_REQUEST)
        if len(password) < 8:
            return response.Response({"error": "La contraseña debe tener al menos 8 caracteres"}, status=status.HTTP_400_BAD_REQUEST)
        if User.objects.filter(username=email).exists():
            return response.Response({"error": f"Ya existe un usuario con el email '{email}'"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                # username = email para que el JWT login funcione con el campo email del formulario
                user = User.objects.create_user(username=email, email=email, password=password)
                if username:
                    user.first_name = username
                    user.save(update_fields=["first_name"])
                profile = models.UserProfile.objects.create(user=user, tenant=tenant, role=role)
        except Exception as e:
            return response.Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return response.Response({
            "id": user.pk,
            "username": user.first_name or user.email,
            "email": user.email,
            "role": profile.role,
            "is_active": user.is_active,
        }, status=status.HTTP_201_CREATED)

    @decorators.action(detail=True, methods=["patch", "delete"], url_path="users/(?P<user_id>[^/.]+)", url_name="user-detail")
    def user_detail(self, request, pk=None, user_id=None):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        tenant = self.get_object()
        try:
            profile = models.UserProfile.objects.select_related("user").get(tenant=tenant, user_id=user_id)
        except models.UserProfile.DoesNotExist:
            return response.Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        if request.method == "DELETE":
            profile.user.delete()
            return response.Response(status=status.HTTP_204_NO_CONTENT)

        # PATCH — actualizar usuario
        user = profile.user
        try:
            with transaction.atomic():
                if "username" in request.data:
                    # username es el nombre visible, guardado en first_name
                    user.first_name = request.data["username"].strip()
                if "email" in request.data:
                    new_email = request.data["email"].strip()
                    if new_email != user.email:
                        if User.objects.filter(username=new_email).exclude(pk=user.pk).exists():
                            return response.Response({"error": f"Ya existe un usuario con el email '{new_email}'"}, status=status.HTTP_400_BAD_REQUEST)
                        user.username = new_email  # username == email para JWT login
                        user.email = new_email
                if "password" in request.data and request.data["password"]:
                    pwd = request.data["password"]
                    if len(pwd) < 8:
                        return response.Response({"error": "La contraseña debe tener al menos 8 caracteres"}, status=status.HTTP_400_BAD_REQUEST)
                    user.set_password(pwd)
                user.save()
                if "role" in request.data:
                    profile.role = request.data["role"]
                    profile.save(update_fields=["role"])
        except Exception as e:
            return response.Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return response.Response({
            "id": user.pk,
            "username": user.first_name or user.email,
            "email": user.email,
            "role": profile.role,
            "is_active": user.is_active,
        })


class MeView(drf_views.APIView):
    """GET /api/v1/auth/me/ — identidad y tenant del usuario autenticado.

    Sirve para que el frontend sepa a qué restaurante pertenece el usuario y
    para diagnosticar usuarios sin perfil/tenant (no aislados correctamente).
    """
    def get(self, request):
        u = request.user
        profile = getattr(u, "profile", None)
        tenant = profile.tenant if profile else None
        resolved = resolve_tenant_id(u)
        return response.Response({
            "id": u.id,
            "username": u.get_username(),
            "email": u.email,
            "isSuperuser": u.is_superuser,
            "hasProfile": profile is not None,
            "role": getattr(profile, "role", None),
            "tenantId": str(tenant.id) if tenant else None,
            "tenantName": tenant.name if tenant else None,
            "resolvedTenantId": str(resolved) if resolved else None,
        })


class AdminMetricsView(drf_views.APIView):
    """GET /api/v1/admin/metrics/ — métricas SaaS globales (solo superadmin)."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        from django.db.models.functions import TruncMonth
        tenants = models.Tenant.objects.all()
        total = tenants.count()
        active = tenants.filter(status="active").count()
        trial = tenants.filter(status="trial").count()
        churned = tenants.filter(status="churned").count()

        PLAN_MRR = {"starter": 299000, "growth": 599000, "enterprise": 1200000}
        mrr_total = sum(PLAN_MRR.get(t.plan, 0) for t in tenants if t.status in ("active", "trial"))
        arpa = mrr_total / max(active + trial, 1)
        churn = round(churned / max(total, 1) * 100, 1)

        spark = [0] * 7

        kpis = [
            {"id": "tenants", "label": "Restaurantes", "value": total, "format": "number",
             "delta": 0, "icon": "Building2", "spark": spark},
            {"id": "mrr", "label": "MRR Total", "value": mrr_total, "format": "currency",
             "delta": 0, "icon": "TrendingUp", "spark": spark},
            {"id": "active", "label": "Activos", "value": active, "format": "number",
             "delta": 0, "icon": "CheckCircle", "spark": spark},
            {"id": "churn", "label": "Churn", "value": churn, "format": "percent",
             "delta": 0, "icon": "TrendingDown", "spark": spark},
        ]

        # MRR trend: últimos 6 meses (basado en fecha de creación de tenants)
        MONTHS_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
        from django.utils import timezone
        today = timezone.localdate()
        mrr_trend = []
        for i in range(5, -1, -1):
            from datetime import date
            m = (today.month - i - 1) % 12 + 1
            y = today.year if today.month - i > 0 else today.year - 1
            count = tenants.filter(created_at__year__lte=y, created_at__month__lte=m if y == today.year else 12).count()
            val = sum(PLAN_MRR.get(t.plan, 0) for t in tenants.filter(status__in=("active","trial")))
            mrr_trend.append({"label": MONTHS_ES[m - 1], "value": val if i == 0 else val * (0.85 ** i)})

        plan_counts = {p: tenants.filter(plan=p).count() for p in ("starter", "growth", "enterprise")}
        plan_mix = [
            {"name": "Starter", "value": plan_counts["starter"], "color": "#6366f1"},
            {"name": "Growth", "value": plan_counts["growth"], "color": "#10b981"},
            {"name": "Enterprise", "value": plan_counts["enterprise"], "color": "#f59e0b"},
        ]

        return response.Response({
            "kpis": kpis,
            "mrrTrend": mrr_trend,
            "planMix": plan_mix,
            "churn": churn,
            "arpa": arpa,
        })


class SaleViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Sale.objects.all().order_by("-created_at")
    serializer_class = serializers.SaleSerializer
    http_method_names = ["get", "post", "head", "options"]  # read + create only


# ─── WhatsApp ───────────────────────────────────────────────────────────────

class WhatsAppCustomerViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.WhatsAppCustomer.objects.all().order_by("-last_order_at")
    serializer_class = serializers.WhatsAppCustomerSerializer

    @decorators.action(detail=False, methods=["post"], url_path="upsert")
    def upsert(self, request):
        """Create or update customer by phone number."""
        tenant_id = self._resolve_tenant_id()
        phone = request.data.get("phone", "").strip()
        if not phone:
            return response.Response({"error": "phone required"}, status=status.HTTP_400_BAD_REQUEST)
        customer, created = models.WhatsAppCustomer.objects.get_or_create(
            tenant_id=tenant_id, phone=phone,
            defaults={"name": request.data.get("name", "Cliente")},
        )
        for field in ("name", "address", "latitude", "longitude"):
            if field in request.data and request.data[field]:
                setattr(customer, field, request.data[field])
        if not created:
            customer.save()
        return response.Response(serializers.WhatsAppCustomerSerializer(customer).data)


class WhatsAppOrderViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.WhatsAppOrder.objects.prefetch_related("lines").order_by("-created_at")
    serializer_class = serializers.WhatsAppOrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status__in=[s.strip() for s in status_param.split(",")])
        return qs

    def perform_create(self, serializer):
        tenant_id = self._resolve_tenant_id()
        order = serializer.save(tenant_id=tenant_id)
        # Link to WhatsAppCustomer and increment order count
        try:
            customer = models.WhatsAppCustomer.objects.get(tenant_id=tenant_id, phone=order.phone)
            order.wa_customer = customer
            order.save(update_fields=["wa_customer"])
            customer.order_count = models.WhatsAppOrder.objects.filter(wa_customer=customer).count()
            customer.last_order_at = order.created_at
            customer.save(update_fields=["order_count", "last_order_at"])
        except models.WhatsAppCustomer.DoesNotExist:
            pass

    @decorators.action(detail=True, methods=["patch"], url_path="receipt")
    def update_receipt(self, request, pk=None):
        order = self.get_object()
        order.receipt_url = request.data.get("receiptUrl", "")
        order.save(update_fields=["receipt_url"])
        return response.Response(serializers.WhatsAppOrderSerializer(order).data)


class WhatsAppConfigViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.WhatsAppConfig.objects.all()
    serializer_class = serializers.WhatsAppConfigSerializer

    def list(self, request, *args, **kwargs):
        tenant_id = self._resolve_tenant_id()
        config, _ = models.WhatsAppConfig.objects.get_or_create(
            tenant_id=tenant_id,
            defaults={"restaurant_name": "", "greeting": ""},
        )
        return response.Response(serializers.WhatsAppConfigSerializer(config).data)

    def perform_create(self, serializer):
        tenant_id = self._resolve_tenant_id()
        existing = models.WhatsAppConfig.objects.filter(tenant_id=tenant_id).first()
        if existing:
            for attr, value in serializer.validated_data.items():
                setattr(existing, attr, value)
            existing.save()
        else:
            serializer.save(tenant_id=tenant_id)


# ─── Analytics ───────────────────────────────────────────────────────────────

def _tenant_qs(model_qs, user):
    tenant_id = resolve_tenant_id(user)
    return model_qs.filter(tenant_id=tenant_id) if tenant_id else model_qs.none()


def _delta(current, previous):
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) / previous * 100, 1)


DAYS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MONTHS_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"]
METHOD_LABELS = {"card": "Tarjeta", "cash": "Efectivo", "transfer": "Transferencia", "nequi": "Nequi"}


class DashboardView(drf_views.APIView):
    """GET /api/v1/dashboard/summary/ — métricas en tiempo real."""

    def get(self, request):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        sale_qs = _tenant_qs(models.Sale.objects.all(), request.user)
        inv_qs = _tenant_qs(models.InventoryItem.objects.all(), request.user)
        table_qs = _tenant_qs(models.Table.objects.all(), request.user)
        order_qs = _tenant_qs(models.Order.objects.all(), request.user)

        # Daily revenue last 30 days (one query)
        daily = {
            r["day"]: float(r["total"])
            for r in (
                sale_qs
                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(total=Sum("total"))
            )
        }
        rev_today = daily.get(today, 0.0)
        rev_yday = daily.get(yesterday, 0.0)

        orders_today = sale_qs.filter(created_at__date=today).count()
        orders_yday = sale_qs.filter(created_at__date=yesterday).count()
        avg_today = rev_today / orders_today if orders_today else 0.0
        avg_yday = rev_yday / orders_yday if orders_yday else 0.0

        # Spark: last 7 days
        spark_rev = [daily.get(today - timedelta(days=i), 0.0) for i in range(6, -1, -1)]
        spark_ord = [
            sale_qs.filter(created_at__date=today - timedelta(days=i)).count()
            for i in range(6, -1, -1)
        ]

        critical_count = inv_qs.filter(status="critical").count()

        kpis = [
            {"id": "revenue", "label": "Ventas Hoy", "value": rev_today, "format": "currency",
             "delta": _delta(rev_today, rev_yday), "icon": "DollarSign", "spark": spark_rev},
            {"id": "orders", "label": "Órdenes Hoy", "value": orders_today, "format": "number",
             "delta": _delta(orders_today, orders_yday), "icon": "ShoppingBag", "spark": spark_ord},
            {"id": "avg_ticket", "label": "Ticket Promedio", "value": round(avg_today, 0), "format": "currency",
             "delta": _delta(avg_today, avg_yday), "icon": "Receipt", "spark": spark_rev},
            {"id": "critical_stock", "label": "Stock Crítico", "value": critical_count, "format": "number",
             "delta": 0.0, "icon": "AlertTriangle", "spark": [critical_count] * 7},
        ]

        # Sales by hour (today)
        hourly = {
            r["h"]: float(r["total"])
            for r in (
                sale_qs
                .filter(created_at__date=today)
                .annotate(h=ExtractHour("created_at"))
                .values("h")
                .annotate(total=Sum("total"))
            )
        }
        sales_by_hour = [{"label": f"{h:02d}:00", "value": hourly.get(h, 0.0)} for h in range(24)]

        # Sales by day (last 7)
        sales_by_day = [
            {"label": DAYS_ES[(today - timedelta(days=i)).weekday()], "value": daily.get(today - timedelta(days=i), 0.0)}
            for i in range(6, -1, -1)
        ]

        # Sales vs last year (monthly)
        current_year = today.year
        monthly_curr = {
            r["m"]: float(r["total"])
            for r in (
                sale_qs.filter(created_at__year=current_year)
                .annotate(m=TruncDate("created_at"))
                .values("created_at__month")
                .annotate(total=Sum("total"))
                .values("created_at__month", "total")
            )
        }
        monthly_prev = {
            r["created_at__month"]: float(r["total"])
            for r in (
                sale_qs.filter(created_at__year=current_year - 1)
                .values("created_at__month")
                .annotate(total=Sum("total"))
            )
        }
        sales_vs_last_year = [
            {"label": MONTHS_ES[m - 1], "current": monthly_curr.get(m, 0.0), "previous": monthly_prev.get(m, 0.0)}
            for m in range(1, 13)
        ]

        # Top products from OrderLines
        tenant_id = resolve_tenant_id(request.user)
        raw_lines = models.OrderLine.objects.filter(order__tenant_id=tenant_id) if tenant_id \
            else models.OrderLine.objects.none()
        top_raw = (
            raw_lines
            .values("product__id", "product__name", "product__image", "product__category__name")
            .annotate(units=Sum("quantity"), revenue=Sum(F("quantity") * F("unit_price")))
            .order_by("-revenue")[:10]
        )
        top_products = [
            {
                "id": str(r["product__id"]),
                "name": r["product__name"],
                "category": r["product__category__name"] or "",
                "units": r["units"] or 0,
                "revenue": float(r["revenue"] or 0),
                "image": r["product__image"] or "🍽️",
            }
            for r in top_raw
        ]

        # Alerts
        alerts = []
        for item in inv_qs.filter(status="critical")[:5]:
            alerts.append({
                "id": str(item.id), "type": "stock", "severity": "critical",
                "title": f"Stock crítico: {item.name}",
                "description": f"Solo {float(item.stock):.1f} {item.unit} (mín: {float(item.min_stock):.1f})",
                "time": item.updated_at.isoformat(),
            })
        for item in inv_qs.filter(status="low")[:3]:
            alerts.append({
                "id": f"low-{item.id}", "type": "stock", "severity": "warning",
                "title": f"Stock bajo: {item.name}",
                "description": f"{float(item.stock):.1f} {item.unit} disponibles (mín: {float(item.min_stock):.1f})",
                "time": item.updated_at.isoformat(),
            })

        occupied = table_qs.filter(status__in=["occupied", "billing"]).count()
        total_tables = table_qs.count()
        active_orders = order_qs.filter(status__in=["pending", "preparing"]).count()

        return response.Response({
            "kpis": kpis,
            "salesByHour": sales_by_hour,
            "salesByDay": sales_by_day,
            "salesVsLastYear": sales_vs_last_year,
            "topProducts": top_products,
            "alerts": alerts,
            "occupancy": {"occupied": occupied, "total": total_tables},
            "kitchenLoad": {"active": active_orders, "avgMinutes": 15},
            "criticalStock": critical_count,
        })


class ReportsView(drf_views.APIView):
    """GET /api/v1/reports/executive/ — resumen ejecutivo últimos 30 días."""

    def get(self, request):
        today = timezone.localdate()
        start_30 = today - timedelta(days=29)
        start_60 = today - timedelta(days=59)

        sale_qs = _tenant_qs(models.Sale.objects.all(), request.user)
        tenant_id = resolve_tenant_id(request.user)
        line_qs = models.OrderLine.objects.filter(order__tenant_id=tenant_id) if tenant_id \
            else models.OrderLine.objects.none()

        curr = sale_qs.filter(created_at__date__gte=start_30)
        prev = sale_qs.filter(created_at__date__gte=start_60, created_at__date__lt=start_30)

        curr_rev = float(curr.aggregate(t=Sum("total"))["t"] or 0)
        prev_rev = float(prev.aggregate(t=Sum("total"))["t"] or 0)
        curr_ord = curr.count()
        prev_ord = prev.count()
        curr_avg = curr_rev / curr_ord if curr_ord else 0.0
        prev_avg = prev_rev / prev_ord if prev_ord else 0.0
        curr_profit = curr_rev * 0.35
        prev_profit = prev_rev * 0.35

        # Daily data — one query
        daily = {
            r["day"]: float(r["total"])
            for r in (
                sale_qs
                .filter(created_at__date__gte=start_30)
                .annotate(day=TruncDate("created_at"))
                .values("day")
                .annotate(total=Sum("total"))
            )
        }
        spark = [daily.get(today - timedelta(days=i), 0.0) for i in range(6, -1, -1)]

        kpis = [
            {"id": "revenue", "label": "Ingresos 30d", "value": curr_rev, "format": "currency",
             "delta": _delta(curr_rev, prev_rev), "icon": "TrendingUp", "spark": spark},
            {"id": "profit", "label": "Utilidad Est. 30d", "value": round(curr_profit, 0), "format": "currency",
             "delta": _delta(curr_profit, prev_profit), "icon": "PiggyBank", "spark": [round(v * 0.35, 0) for v in spark]},
            {"id": "orders", "label": "Órdenes 30d", "value": curr_ord, "format": "number",
             "delta": _delta(curr_ord, prev_ord), "icon": "ShoppingBag", "spark": spark},
            {"id": "avg_ticket", "label": "Ticket Promedio", "value": round(curr_avg, 0), "format": "currency",
             "delta": _delta(curr_avg, prev_avg), "icon": "Receipt", "spark": spark},
        ]

        revenue_trend = [
            {"label": (today - timedelta(days=29 - i)).strftime("%d/%m"), "value": daily.get(today - timedelta(days=29 - i), 0.0)}
            for i in range(30)
        ]
        profit_trend = [{"label": p["label"], "value": round(p["value"] * 0.35, 0)} for p in revenue_trend]

        # Category mix from OrderLines
        cat_agg = (
            line_qs
            .filter(order__created_at__date__gte=start_30)
            .values("product__category__name")
            .annotate(revenue=Sum(F("quantity") * F("unit_price")))
            .order_by("-revenue")
        )
        category_mix = [
            {"name": r["product__category__name"] or "Sin categoría", "value": float(r["revenue"] or 0), "color": COLORS[i % len(COLORS)]}
            for i, r in enumerate(cat_agg)
        ]

        # Channel mix from Sale.sale_type
        channel_agg = (
            curr.values("sale_type").annotate(revenue=Sum("total")).order_by("-revenue")
        )
        channel_mix = [
            {"name": r["sale_type"] or "Mesa", "value": float(r["revenue"] or 0), "color": COLORS[i % len(COLORS)]}
            for i, r in enumerate(channel_agg)
        ]

        # Payment mix
        pay_agg = curr.values("method").annotate(revenue=Sum("total")).order_by("-revenue")
        payment_mix = [
            {"name": METHOD_LABELS.get(r["method"], r["method"] or "Otro"), "value": float(r["revenue"] or 0), "color": COLORS[i % len(COLORS)]}
            for i, r in enumerate(pay_agg)
        ]

        # Sales by location
        loc_agg = curr.values("sale_type").annotate(total_rev=Sum("total"), cnt=Count("id")).order_by("-total_rev")
        sales_by_location = [
            {"name": r["sale_type"] or "Sin tipo", "value": float(r["total_rev"] or 0), "avg": float(r["total_rev"] or 0) / max(r["cnt"], 1)}
            for r in loc_agg
        ]

        # Top dishes from OrderLines
        top_raw = (
            line_qs
            .filter(order__created_at__date__gte=start_30)
            .values("product__name")
            .annotate(units=Sum("quantity"), revenue=Sum(F("quantity") * F("unit_price")))
            .order_by("-revenue")[:10]
        )
        top_dishes = [
            {"name": r["product__name"], "units": r["units"] or 0, "revenue": float(r["revenue"] or 0),
             "avg": float(r["revenue"] or 0) / max(r["units"] or 1, 1)}
            for r in top_raw
        ]

        # Hourly heat (all time)
        hourly = {
            r["h"]: float(r["total"])
            for r in (
                sale_qs
                .annotate(h=ExtractHour("created_at"))
                .values("h")
                .annotate(total=Sum("total"))
            )
        }
        hourly_heat = [{"label": f"{h:02d}:00", "value": hourly.get(h, 0.0)} for h in range(24)]

        return response.Response({
            "kpis": kpis,
            "revenueTrend": revenue_trend,
            "profitTrend": profit_trend,
            "categoryMix": category_mix,
            "channelMix": channel_mix,
            "paymentMix": payment_mix,
            "salesByLocation": sales_by_location,
            "topDishes": top_dishes,
            "hourlyHeat": hourly_heat,
        })
