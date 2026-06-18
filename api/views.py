"""
ViewSets DRF. Cada uno filtra por el tenant del usuario autenticado
(aislamiento multi-tenant) y mapea a los endpoints que el frontend ya llama.
"""
from rest_framework import viewsets, decorators, response
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from . import models, serializers


class TenantQuerySet:
    """Mixin: limita el queryset al restaurante del usuario."""
    def get_queryset(self):
        qs = super().get_queryset()
        tenant = getattr(self.request.user, "tenant_id", None)
        return qs.filter(tenant_id=tenant) if tenant else qs.none()


class CategoryViewSet(TenantQuerySet, viewsets.ReadOnlyModelViewSet):
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
        qs = models.InventoryMovement.objects.filter(item__tenant_id=request.user.tenant_id)
        return response.Response(serializers.InventoryMovementSerializer(qs, many=True).data)


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
        order = serializer.save(tenant_id=self.request.user.tenant_id)
        # Empuja el ticket a la cocina por WebSocket (Channels)
        layer = get_channel_layer()
        async_to_sync(layer.group_send)(
            f"kitchen_{order.tenant_id}",
            {"type": "ticket.new", "ticket": serializers.OrderSerializer(order).data},
        )
