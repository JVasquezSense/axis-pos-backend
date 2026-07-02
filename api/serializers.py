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
        fields = ["id", "name", "description", "price", "category", "image", "tags", "available", "prepMinutes", "popular"]


class InventoryItemSerializer(serializers.ModelSerializer):
    minStock = serializers.DecimalField(source="min_stock", max_digits=12, decimal_places=3)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = models.InventoryItem
        fields = ["id", "name", "category", "stock", "unit", "minStock", "cost", "supplier", "status", "updatedAt"]


class InventoryMovementSerializer(serializers.ModelSerializer):
    inventoryId = serializers.PrimaryKeyRelatedField(source="item", read_only=True)
    unitCost = serializers.DecimalField(source="unit_cost", max_digits=12, decimal_places=2)
    date = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.InventoryMovement
        fields = ["id", "inventoryId", "date", "type", "quantity", "balance", "unitCost", "reason"]


class OrderLineSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    unitPrice = serializers.DecimalField(source="unit_price", max_digits=12, decimal_places=2)

    class Meta:
        model = models.OrderLine
        fields = ["id", "product", "quantity", "notes", "unitPrice"]


class OrderSerializer(serializers.ModelSerializer):
    lines = OrderLineSerializer(many=True, read_only=True)
    tableNumber = serializers.IntegerField(source="table.number", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = models.Order
        fields = ["id", "code", "tableNumber", "channel", "status", "lines", "customer", "phone", "receipt", "createdAt"]


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
    name = serializers.CharField(source="inventory_item.name", read_only=True)

    class Meta:
        model = models.PurchaseLine
        fields = ["id", "inventoryId", "name", "quantity", "unit", "unitCost"]


class PurchaseSerializer(serializers.ModelSerializer):
    lines = PurchaseLineSerializer(many=True)
    supplierId = serializers.PrimaryKeyRelatedField(
        source="supplier", queryset=models.Supplier.objects.all(), write_only=True
    )
    supplierName = serializers.CharField(source="supplier.name", read_only=True)
    invoicePhoto = serializers.CharField(source="invoice_photo", required=False, allow_blank=True, default="")

    class Meta:
        model = models.Purchase
        fields = ["id", "code", "supplierId", "supplierName", "date", "total", "lines", "invoicePhoto"]
        read_only_fields = ["date", "supplierName"]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        purchase = models.Purchase.objects.create(**validated_data)
        for line_data in lines_data:
            inv_item = line_data.pop("inventory_item")
            pl = models.PurchaseLine.objects.create(
                purchase=purchase, inventory_item=inv_item, **line_data
            )
            # Actualiza stock en inventario y crea movimiento
            inv_item.stock = float(inv_item.stock) + float(pl.quantity)
            inv_item.recompute_status()
            inv_item.save()
            models.InventoryMovement.objects.create(
                tenant=purchase.tenant,
                item=inv_item,
                type="entrada",
                quantity=pl.quantity,
                balance=inv_item.stock,
                unit_cost=pl.unit_cost,
                reason=f"Compra {purchase.code} · {purchase.supplier.name}",
            )
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
        fields = ["id", "total", "items", "method", "saleType", "table", "tip", "waiter", "ts"]
        read_only_fields = ["ts"]
