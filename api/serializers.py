"""Serializers DRF: producen el mismo JSON (camelCase) que la UI ya consume."""
from rest_framework import serializers
from . import models


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
        fields = ["id", "number", "capacity", "zone", "status", "waiter", "seatedAt"]


class CustomerSerializer(serializers.ModelSerializer):
    totalSpent = serializers.DecimalField(source="total_spent", max_digits=14, decimal_places=2)
    lastVisit = serializers.DateField(source="last_visit", read_only=True)

    class Meta:
        model = models.Customer
        fields = ["id", "name", "phone", "email", "totalSpent", "visits", "points", "tier", "lastVisit"]


class RecipeIngredientSerializer(serializers.ModelSerializer):
    inventoryId = serializers.PrimaryKeyRelatedField(source="item", queryset=models.InventoryItem.objects.all())

    class Meta:
        model = models.RecipeIngredient
        fields = ["id", "inventoryId", "quantity", "waste"]


class RecipeSerializer(serializers.ModelSerializer):
    ingredients = RecipeIngredientSerializer(many=True)
    productId = serializers.PrimaryKeyRelatedField(source="product", queryset=models.Product.objects.all(), required=False)

    class Meta:
        model = models.Recipe
        fields = ["id", "name", "emoji", "productId", "station", "portions", "price", "ingredients"]

    def create(self, validated_data):
        ingredients = validated_data.pop("ingredients", [])
        recipe = models.Recipe.objects.create(**validated_data)
        for ing in ingredients:
            models.RecipeIngredient.objects.create(recipe=recipe, **ing)
        return recipe
