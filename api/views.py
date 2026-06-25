"""
ViewSets DRF. Cada uno filtra por el tenant del usuario autenticado
(aislamiento multi-tenant) y mapea a los endpoints que el frontend ya llama.
"""
from rest_framework import viewsets, decorators, response, status
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from . import models, serializers


class TenantQuerySet:
    """
    Mixin: limita el queryset al restaurante del usuario.
    Si el usuario aún no tiene tenant asignado (despliegue single-tenant o
    acceso de lectura), devuelve todo para que la API funcione de inmediato.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        tenant = getattr(self.request.user, "tenant_id", None)
        return qs.filter(tenant_id=tenant) if tenant else qs

    def perform_create(self, serializer):
        tenant_id = getattr(self.request.user, "tenant_id", None)
        if tenant_id:
            serializer.save(tenant_id=tenant_id)
        else:
            serializer.save()


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
        tenant_id = getattr(request.user, "tenant_id", None)
        qs = models.InventoryMovement.objects.filter(item__tenant_id=tenant_id) if tenant_id \
            else models.InventoryMovement.objects.all()
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
    queryset = models.Order.objects.prefetch_related("lines")
    serializer_class = serializers.OrderSerializer

    def perform_create(self, serializer):
        tenant_id = getattr(self.request.user, "tenant_id", None)
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


# ─── Proveedores ──────────────────────────────────────────────────────────────

class SupplierViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Supplier.objects.all()
    serializer_class = serializers.SupplierSerializer


class PurchaseViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Purchase.objects.prefetch_related("lines__inventory_item").select_related("supplier")
    serializer_class = serializers.PurchaseSerializer

    def perform_create(self, serializer):
        tenant_id = getattr(self.request.user, "tenant_id", None)
        if tenant_id:
            serializer.save(tenant_id=tenant_id)
        else:
            serializer.save()


# ─── Reservaciones ───────────────────────────────────────────────────────────

class ReservationViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Reservation.objects.all().order_by("date", "time")
    serializer_class = serializers.ReservationSerializer


# ─── Empleados ───────────────────────────────────────────────────────────────

class EmployeeViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Employee.objects.all().order_by("name")
    serializer_class = serializers.EmployeeSerializer


# ─── Ventas ──────────────────────────────────────────────────────────────────

class SaleViewSet(TenantQuerySet, viewsets.ModelViewSet):
    queryset = models.Sale.objects.all().order_by("-created_at")
    serializer_class = serializers.SaleSerializer
    http_method_names = ["get", "post", "head", "options"]  # read + create only
