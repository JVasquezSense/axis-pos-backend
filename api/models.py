"""
Modelos de dominio de Axis POS.
Reflejan 1:1 los tipos del frontend (src/types/index.ts) para que los
serializers de DRF produzcan exactamente el JSON que la UI ya consume.
Todo es multi-tenant: cada fila pertenece a un Tenant (restaurante).
"""
import uuid
from django.db import models


class Tenant(models.Model):
    PLAN = [("starter", "Starter"), ("growth", "Growth"), ("enterprise", "Enterprise")]
    STATUS = [("active", "Activo"), ("trial", "Prueba"), ("past_due", "Mora"), ("churned", "Cancelado")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    logo = models.CharField(max_length=8, default="🍔")
    plan = models.CharField(max_length=20, choices=PLAN, default="starter")
    status = models.CharField(max_length=20, choices=STATUS, default="trial")
    city = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TenantScoped(models.Model):
    """Base abstracta: aísla los datos por restaurante."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="%(class)ss")

    class Meta:
        abstract = True


class Category(TenantScoped):
    name = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, default="Utensils")

    class Meta:
        verbose_name_plural = "categories"


class Product(TenantScoped):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    image = models.CharField(max_length=8, default="🍽️")
    tags = models.JSONField(default=list)
    available = models.BooleanField(default=True)
    prep_minutes = models.PositiveIntegerField(default=10)
    popular = models.BooleanField(default=False)


class InventoryItem(TenantScoped):
    STATUS = [("normal", "Normal"), ("low", "Bajo"), ("critical", "Crítico")]
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=80)
    stock = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=16)
    min_stock = models.DecimalField(max_digits=12, decimal_places=3)
    cost = models.DecimalField(max_digits=12, decimal_places=2)
    supplier = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="normal")
    updated_at = models.DateTimeField(auto_now=True)

    def recompute_status(self):
        if self.stock <= self.min_stock * 0.4:
            self.status = "critical"
        elif self.stock < self.min_stock:
            self.status = "low"
        else:
            self.status = "normal"


class InventoryMovement(TenantScoped):
    TYPE = [("inicial", "Inicial"), ("entrada", "Entrada"), ("salida", "Salida"), ("ajuste", "Ajuste")]
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="movements")
    type = models.CharField(max_length=12, choices=TYPE)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    balance = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Recipe(TenantScoped):
    STATION = [("grill", "Parrilla"), ("fry", "Freidora"), ("cold", "Fríos"), ("bar", "Barra"), ("pastry", "Pastelería")]
    name = models.CharField(max_length=120)
    emoji = models.CharField(max_length=8, default="🍽️")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="recipes")
    station = models.CharField(max_length=12, choices=STATION, default="grill")
    portions = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    waste = models.FloatField(default=0)  # 0..1


class Table(TenantScoped):
    STATUS = [("available", "Disponible"), ("occupied", "Ocupada"), ("reserved", "Reservada"), ("billing", "Cuenta")]
    number = models.PositiveIntegerField()
    capacity = models.PositiveIntegerField(default=4)
    zone = models.CharField(max_length=60, default="Salón")
    status = models.CharField(max_length=12, choices=STATUS, default="available")
    waiter = models.CharField(max_length=80, blank=True)
    seated_at = models.DateTimeField(null=True, blank=True)


class Order(TenantScoped):
    CHANNEL = [("dine_in", "Mesa"), ("takeaway", "Para llevar"), ("delivery", "Domicilio"), ("web", "Web")]
    STATUS = [("pending", "Pendiente"), ("preparing", "Preparando"), ("ready", "Listo"), ("served", "Servido"), ("paid", "Pagado")]
    code = models.CharField(max_length=16)
    table = models.ForeignKey(Table, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    channel = models.CharField(max_length=12, choices=CHANNEL, default="dine_in")
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    customer = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    receipt = models.FileField(upload_to="receipts/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    notes = models.CharField(max_length=200, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)


class Customer(TenantScoped):
    TIER = [("bronze", "Bronce"), ("silver", "Plata"), ("gold", "Oro"), ("platinum", "Platino")]
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    total_spent = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    visits = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    tier = models.CharField(max_length=12, choices=TIER, default="bronze")
    last_visit = models.DateField(null=True, blank=True)
