"""Serializers DRF: producen el mismo JSON (camelCase) que la UI ya consume."""
from rest_framework import serializers
from . import models


class NullablePKField(serializers.PrimaryKeyRelatedField):
    """
    PrimaryKeyRelatedField que acepta "" y strings no-enteras como null.
    El frontend genera IDs cliente temporales (p.ej. "inv-abc123") mientras
    espera la respuesta del backend; si llega un string no válido se trata
    como null en lugar de lanzar un 400.
    """
    def to_internal_value(self, data):
        if data in (None, "", "null", "undefined"):
            if self.allow_null:
                return None
            self.fail("null")
        try:
            int(data)
        except (ValueError, TypeError):
            if self.allow_null:
                return None
        return super().to_internal_value(data)


class CategorySerializer(serializers.ModelSerializer):
    count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = models.Category
        fields = ["id", "name", "icon", "count"]


class ProductSerializer(serializers.ModelSerializer):
    prepMinutes = serializers.IntegerField(source="prep_minutes")

    class Meta:
        model = models.Product
        fields = ["id", "name", "description", "price", "category", "image", "tags", "available", "prepMinutes", "popular", "restockable"]


class InventoryItemSerializer(serializers.ModelSerializer):
    minStock = serializers.DecimalField(source="min_stock", max_digits=12, decimal_places=3)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = models.InventoryItem
        fields = ["id", "name", "category", "stock", "unit", "minStock", "cost", "supplier", "status", "updatedAt"]

    def create(self, validated_data):
        """
        Al crear un insumo se registra su movimiento "inicial" en el kardex,
        con balance = stock inicial. Así el saldo inicial del kardex nunca
        aparece en 0 y los movimientos posteriores encadenan correctamente.
        El tenant lo inyecta InventoryViewSet.perform_create (TenantQuerySet).
        """
        stock = validated_data.get("stock", 0)
        item = models.InventoryItem.objects.create(**validated_data)
        item.recompute_status()
        item.save(update_fields=["status"])
        models.InventoryMovement.objects.create(
            tenant=item.tenant,
            item=item,
            type="inicial",
            quantity=stock,
            balance=stock,
            unit_cost=item.cost,
            reason=f"Saldo inicial · {item.name}",
        )
        return item


class InventoryMovementSerializer(serializers.ModelSerializer):
    inventoryId = serializers.PrimaryKeyRelatedField(source="item", read_only=True)
    unitCost = serializers.DecimalField(source="unit_cost", max_digits=12, decimal_places=2)
    date = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.InventoryMovement
        fields = ["id", "inventoryId", "date", "type", "quantity", "balance", "unitCost", "reason"]


class OrderLineSerializer(serializers.ModelSerializer):
    productId = serializers.PrimaryKeyRelatedField(
        source="product", queryset=models.Product.objects.all(), write_only=True
    )
    product = ProductSerializer(read_only=True)
    unitPrice = serializers.DecimalField(source="unit_price", max_digits=12, decimal_places=2)

    class Meta:
        model = models.OrderLine
        fields = ["id", "productId", "product", "quantity", "notes", "unitPrice"]


class OrderSerializer(serializers.ModelSerializer):
    lines = OrderLineSerializer(many=True)
    # Al escribir, el frontend solo conoce el NÚMERO de mesa (no el PK interno).
    table = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    tableNumber = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.Order
        fields = ["id", "code", "table", "tableNumber", "channel", "status", "lines", "customer", "phone", "receipt", "createdAt"]

    def get_tableNumber(self, obj):
        return obj.table.number if obj.table else None

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        table_number = validated_data.pop("table", None)
        if table_number is not None:
            validated_data["table"] = models.Table.objects.filter(
                tenant_id=validated_data.get("tenant_id"), number=table_number
            ).first()
        order = models.Order.objects.create(**validated_data)
        for line_data in lines_data:
            models.OrderLine.objects.create(order=order, **line_data)
        return order

    def update(self, instance, validated_data):
        # PATCH desde cocina/caja: cambia estado y, si vienen "lines", reemplaza
        # las líneas de la orden (ediciones del KDS: agregar/quitar/modificar).
        lines_data = validated_data.pop("lines", None)
        table_number = validated_data.pop("table", None)
        prev_status = instance.status
        if table_number is not None:
            instance.table = models.Table.objects.filter(
                tenant_id=instance.tenant_id, number=table_number
            ).first()
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        request = self.context.get("request")
        user_label = ""
        if request is not None and getattr(request, "user", None).is_authenticated:
            user_label = request.user.get_username() or getattr(request.user, "email", "") or ""

        if lines_data is not None:
            # Snapshot previo para el log de auditoría (backlog #4).
            before = [
                {"product": ln.product.name, "quantity": ln.quantity, "unit_price": str(ln.unit_price), "notes": ln.notes}
                for ln in instance.lines.all()
            ]
            instance.lines.all().delete()
            for line_data in lines_data:
                models.OrderLine.objects.create(order=instance, **line_data)
            after = [
                {"product": ln.product.name, "quantity": ln.quantity, "unit_price": str(ln.unit_price), "notes": ln.notes}
                for ln in instance.lines.all()
            ]
            models.OrderChangeLog.objects.create(
                tenant=instance.tenant,
                order=instance,
                action="edit",
                user=user_label,
                summary="Líneas modificadas",
                detail={"before": before, "after": after},
            )

        if "status" in validated_data and validated_data["status"] != prev_status:
            models.OrderChangeLog.objects.create(
                tenant=instance.tenant,
                order=instance,
                action="status",
                user=user_label,
                summary=f"{prev_status} → {instance.status}",
                detail={"from": prev_status, "to": instance.status},
            )
        return instance


class TableSerializer(serializers.ModelSerializer):
    seatedAt = serializers.DateTimeField(source="seated_at", read_only=True)

    class Meta:
        model = models.Table
        fields = ["id", "number", "capacity", "zone", "status", "waiter", "seatedAt", "x", "y", "shape"]


class CustomerSerializer(serializers.ModelSerializer):
    totalSpent = serializers.DecimalField(source="total_spent", max_digits=14, decimal_places=2)
    lastVisit = serializers.DateField(source="last_visit", read_only=True)

    class Meta:
        model = models.Customer
        fields = ["id", "name", "phone", "email", "totalSpent", "visits", "points", "tier", "lastVisit"]


class RecipeIngredientSerializer(serializers.ModelSerializer):
    inventoryId = NullablePKField(
        source="item", queryset=models.InventoryItem.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = models.RecipeIngredient
        fields = ["id", "inventoryId", "name", "unit", "quantity", "waste"]


class RecipeSerializer(serializers.ModelSerializer):
    ingredients = RecipeIngredientSerializer(many=True)
    productId = NullablePKField(
        source="product", queryset=models.Product.objects.all(), required=False, allow_null=True
    )
    prepMinutes = serializers.IntegerField(source="prep_minutes", default=10)
    allergensOther = serializers.CharField(source="allergens_other", allow_blank=True, default="")
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = models.Recipe
        fields = [
            "id", "name", "emoji", "description", "category",
            "productId", "station", "status", "difficulty",
            "portions", "prepMinutes", "price",
            "ingredients", "variations", "steps",
            "allergens", "allergensOther", "tags", "updatedAt",
        ]

    def create(self, validated_data):
        ingredients = validated_data.pop("ingredients", [])
        recipe = models.Recipe.objects.create(**validated_data)
        for ing in ingredients:
            models.RecipeIngredient.objects.create(recipe=recipe, **ing)
        return recipe

    def update(self, instance, validated_data):
        ingredients = validated_data.pop("ingredients", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if ingredients is not None:
            instance.ingredients.all().delete()
            for ing in ingredients:
                models.RecipeIngredient.objects.create(recipe=instance, **ing)
        return instance


# ─── Proveedores ──────────────────────────────────────────────────────────────

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Supplier
        fields = ["id", "name", "contact", "phone", "email", "category", "nit", "active"]


class PurchaseLineSerializer(serializers.ModelSerializer):
    inventoryId = serializers.PrimaryKeyRelatedField(
        source="inventory_item", queryset=models.InventoryItem.objects.all()
    )
    unitCost = serializers.DecimalField(source="unit_cost", max_digits=12, decimal_places=2)
    taxRate = serializers.DecimalField(source="tax_rate", max_digits=5, decimal_places=2, required=False, default=0)
    name = serializers.CharField(source="inventory_item.name", read_only=True)

    class Meta:
        model = models.PurchaseLine
        fields = ["id", "inventoryId", "name", "quantity", "unit", "unitCost", "taxRate"]


class PurchaseSerializer(serializers.ModelSerializer):
    lines = PurchaseLineSerializer(many=True)
    supplierId = serializers.PrimaryKeyRelatedField(
        source="supplier", queryset=models.Supplier.objects.all(), write_only=True
    )
    supplierName = serializers.CharField(source="supplier.name", read_only=True)
    invoicePhoto = serializers.CharField(source="invoice_photo", required=False, allow_blank=True, default="")
    taxTotal = serializers.DecimalField(source="tax_total", max_digits=14, decimal_places=2, required=False, default=0)

    class Meta:
        model = models.Purchase
        fields = ["id", "code", "supplierId", "supplierName", "date", "subtotal", "taxTotal", "total", "lines", "invoicePhoto"]
        read_only_fields = ["date", "supplierName"]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        purchase = models.Purchase.objects.create(**validated_data)
        affected_item_ids = []
        for line_data in lines_data:
            inv_item = line_data.pop("inventory_item")
            pl = models.PurchaseLine.objects.create(
                purchase=purchase, inventory_item=inv_item, **line_data
            )
            # Actualiza stock en inventario y crea movimiento
            inv_item.stock = float(inv_item.stock) + float(pl.quantity)
            inv_item.recompute_status()
            inv_item.save()
            affected_item_ids.append(inv_item.id)
            models.InventoryMovement.objects.create(
                tenant=purchase.tenant,
                item=inv_item,
                type="entrada",
                quantity=pl.quantity,
                balance=inv_item.stock,
                unit_cost=pl.unit_cost,
                reason=f"Compra {purchase.code} · {purchase.supplier.name}",
            )
        # Una compra sube stock: puede reactivar productos que estaban "Agotado".
        from .views import sync_products_availability
        sync_products_availability(affected_item_ids)
        return purchase


# ─── Reservaciones ───────────────────────────────────────────────────────────

class ReservationSerializer(serializers.ModelSerializer):
    tableNumber = serializers.IntegerField(source="table_number")

    class Meta:
        model = models.Reservation
        fields = ["id", "name", "phone", "tableNumber", "date", "time", "guests", "notes", "status"]


# ─── Empleados ───────────────────────────────────────────────────────────────

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Employee
        fields = ["id", "name", "role", "active", "phone", "email"]


# ─── Usuarios de tenant ──────────────────────────────────────────────────────

class TenantUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    is_active = serializers.BooleanField(default=True)
    password = serializers.CharField(write_only=True, required=False)

    def to_representation(self, instance):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if isinstance(instance, User):
            role = "admin"
            try:
                role = instance.profile.role
            except Exception:
                pass
            return {
                "id": instance.pk,
                "username": instance.first_name or instance.email,
                "email": instance.email,
                "role": role,
                "is_active": instance.is_active,
            }
        return super().to_representation(instance)


# ─── Super Admin ─────────────────────────────────────────────────────────────

PLAN_MRR = {"starter": 299000, "growth": 599000, "enterprise": 1200000}


class TenantAdminSerializer(serializers.ModelSerializer):
    mrr = serializers.SerializerMethodField()
    users = serializers.SerializerMethodField()
    ordersMonth = serializers.SerializerMethodField()
    joinedAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.Tenant
        fields = [
            "id", "name", "slug", "logo", "plan", "status", "city",
            "locations", "features",
            "mrr", "users", "ordersMonth", "joinedAt",
        ]
        read_only_fields = ["id", "joinedAt", "mrr", "users", "ordersMonth"]

    def get_mrr(self, obj):
        return PLAN_MRR.get(obj.plan, 0)

    def get_users(self, obj):
        from django.contrib.auth import get_user_model
        return 1  # sin user-tenant FK aún

    def get_ordersMonth(self, obj):
        from django.utils import timezone
        now = timezone.now()
        return models.Sale.objects.filter(
            tenant=obj, created_at__year=now.year, created_at__month=now.month
        ).count()


# ─── Ventas ──────────────────────────────────────────────────────────────────

class SaleSerializer(serializers.ModelSerializer):
    saleType = serializers.CharField(source="sale_type")
    table = serializers.IntegerField(source="table_number", allow_null=True)
    waiter = serializers.CharField(allow_blank=True)
    ts = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.Sale
        fields = ["id", "total", "subtotal", "tax", "discount", "items", "method", "saleType",
                  "table", "tip", "waiter", "customer", "observations", "invoiceNumber", "ts"]
        read_only_fields = ["ts", "invoiceNumber"]

    invoiceNumber = serializers.CharField(source="invoice_number", read_only=True)


# ─── WhatsApp ───────────────────────────────────────────────────────────────

class WhatsAppCustomerSerializer(serializers.ModelSerializer):
    orderCount = serializers.IntegerField(source="order_count", read_only=True)
    lastOrderAt = serializers.DateTimeField(source="last_order_at", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.WhatsAppCustomer
        fields = ["id", "phone", "name", "address", "latitude", "longitude", "orderCount", "lastOrderAt", "createdAt"]


class WhatsAppOrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.WhatsAppOrderLine
        fields = ["id", "name", "quantity", "price"]


class WhatsAppOrderSerializer(serializers.ModelSerializer):
    lines = WhatsAppOrderLineSerializer(many=True)
    customerName = serializers.CharField(source="customer_name")
    receiptUrl = serializers.URLField(source="receipt_url", required=False, allow_blank=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.WhatsAppOrder
        fields = ["id", "code", "customerName", "phone", "address", "total", "status", "receiptUrl", "lines", "createdAt"]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        order = models.WhatsAppOrder.objects.create(**validated_data)
        for line in lines_data:
            models.WhatsAppOrderLine.objects.create(order=order, **line)
        return order


class WhatsAppConfigSerializer(serializers.ModelSerializer):
    twilioSid = serializers.CharField(source="twilio_sid", allow_blank=True)
    twilioToken = serializers.CharField(source="twilio_token", allow_blank=True)
    twilioWhatsappNumber = serializers.CharField(source="twilio_whatsapp_number", allow_blank=True)
    glmApiKey = serializers.CharField(source="glm_api_key", allow_blank=True)
    glmModel = serializers.CharField(source="glm_model")
    glmBaseUrl = serializers.URLField(source="glm_base_url")
    restaurantName = serializers.CharField(source="restaurant_name", allow_blank=True)
    menuText = serializers.CharField(source="menu_text", allow_blank=True)
    paymentInfo = serializers.CharField(source="payment_info", allow_blank=True)
    businessInfo = serializers.CharField(source="business_info", allow_blank=True)
    menuPdf = serializers.FileField(source="menu_pdf", required=False, allow_null=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = models.WhatsAppConfig
        fields = [
            "id", "twilioSid", "twilioToken", "twilioWhatsappNumber",
            "glmApiKey", "glmModel", "glmBaseUrl", "enabled", "greeting",
            "restaurantName", "menuText", "paymentInfo", "businessInfo",
            "menuPdf", "updatedAt",
        ]


# ─── Devoluciones (Notas de Crédito) ──────────────────────────────────────────

class CreditNoteLineSerializer(serializers.ModelSerializer):
    productId = serializers.PrimaryKeyRelatedField(
        source="product", queryset=models.Product.objects.all(), write_only=True
    )
    productName = serializers.CharField(source="name", read_only=True)
    unitPrice = serializers.DecimalField(source="unit_price", max_digits=12, decimal_places=2)

    class Meta:
        model = models.CreditNoteLine
        fields = ["id", "productId", "productName", "quantity", "unitPrice", "restocked"]


class CreditNoteSerializer(serializers.ModelSerializer):
    lines = CreditNoteLineSerializer(many=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.CreditNote
        fields = ["id", "code", "sale", "total", "method", "reason", "user", "lines", "createdAt"]
        read_only_fields = ["code", "user"]

    def validate_reason(self, value):
        # Backlog #6: motivo de devolución obligatorio.
        if not value or not value.strip():
            raise serializers.ValidationError("El motivo de la devolución es obligatorio.")
        return value.strip()

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        tenant_id = validated_data.get("tenant_id")
        tenant = models.Tenant.objects.get(pk=tenant_id) if tenant_id else None
        # Correlativo de nota de crédito por tenant.
        seq = (models.CreditNote.objects.filter(tenant=tenant).count() + 1)
        validated_data["code"] = f"NC-{seq:06d}"
        note = models.CreditNote.objects.create(**validated_data)

        # Reintegra inventario solo de productos marcados como restockable.
        for line_data in lines_data:
            product = line_data["product"]
            restocked = False
            if getattr(product, "restockable", True):
                restocked = _restock_product(product, line_data["quantity"], note, tenant)
            models.CreditNoteLine.objects.create(
                note=note,
                product=product,
                name=product.name,
                quantity=line_data["quantity"],
                unit_price=line_data["unit_price"],
                restocked=restocked,
            )
        return note


def _restock_product(product, quantity, note, tenant):
    """
    Reintegra al inventario los insumos de la receta del producto devuelto.
    Genera un InventoryMovement de tipo "entrada" por cada insumo afectado.
    Retorna True si reintegró algo.
    """
    recipe = models.Recipe.objects.filter(product=product, tenant=tenant).prefetch_related("ingredients").first()
    if not recipe:
        return False
    portions = max(recipe.portions, 1)
    reintegrated = False
    affected_item_ids = []
    for ing in recipe.ingredients.all():
        if ing.item_id is None:
            continue
        item = ing.item
        effective = float(ing.quantity) * (1.0 + float(ing.waste or 0))
        qty_back = (effective / portions) * float(quantity)
        item.stock = float(item.stock) + qty_back
        item.recompute_status()
        item.save(update_fields=["stock", "status", "updated_at"])
        affected_item_ids.append(item.id)
        models.InventoryMovement.objects.create(
            tenant=tenant,
            item=item,
            type="entrada",
            quantity=qty_back,
            balance=item.stock,
            unit_cost=item.cost,
            reason=f"Devolución · {note.code}",
        )
        reintegrated = True
    # El reintegro sube stock: puede reactivar productos "Agotado".
    if affected_item_ids:
        from .views import sync_products_availability
        sync_products_availability(affected_item_ids)
    return reintegrated
