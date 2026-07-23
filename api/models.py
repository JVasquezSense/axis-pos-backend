"""
Modelos de dominio de Axis POS.
Reflejan 1:1 los tipos del frontend (src/types/index.ts) para que los
serializers de DRF produzcan exactamente el JSON que la UI ya consume.
Todo es multi-tenant: cada fila pertenece a un Tenant (restaurante).
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils.text import slugify


def _default_features():
    return {
        "pos": True, "kitchen": True, "inventory": True,
        "recipes": True, "salon": True, "reservations": True,
        "crm": True, "suppliers": True, "employees": True,
        "reports": True, "website": True, "web_orders": True,
    }


class Tenant(models.Model):
    PLAN = [("starter", "Starter"), ("growth", "Growth"), ("enterprise", "Enterprise")]
    STATUS = [("active", "Activo"), ("trial", "Prueba"), ("past_due", "Mora"), ("churned", "Cancelado")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    logo = models.TextField(default="🍔")
    plan = models.CharField(max_length=20, choices=PLAN, default="starter")
    status = models.CharField(max_length=20, choices=STATUS, default="trial")
    city = models.CharField(max_length=80, blank=True)
    locations = models.PositiveIntegerField(default=1)
    features = models.JSONField(default=_default_features)
    created_at = models.DateTimeField(auto_now_add=True)
    # Información fiscal para la factura/ticket (backlog #1).
    tax_id = models.CharField(max_length=40, blank=True)        # NIT / RUT
    legal_name = models.CharField(max_length=160, blank=True)   # Razón social
    address = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    resolution = models.CharField(max_length=200, blank=True)   # Resolución DIAN
    invoice_prefix = models.CharField(max_length=12, default="FV")
    invoice_seq = models.PositiveIntegerField(default=0)        # correlativo de factura

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:140] or "restaurante"
            candidate = base
            i = 2
            while Tenant.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{i}"[:140]
                i += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class UserProfile(models.Model):
    ROLE = [("admin","Admin"),("cashier","Cajero"),("waiter","Mesero"),("kitchen","Cocina"),("warehouse","Almacén")]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="profiles", null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE, default="admin")

    def __str__(self):
        return f"{self.user.username} → {self.tenant}"


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
    image = models.TextField(default="🍽️")
    tags = models.JSONField(default=list)
    available = models.BooleanField(default=True)
    prep_minutes = models.PositiveIntegerField(default=10)
    popular = models.BooleanField(default=False)
    # Backlog #6: si el producto se devuelve, ¿reintegra stock? (bebida sellada sí,
    # comida preparada no). Por defecto reintegra (productos sellados).
    restockable = models.BooleanField(default=True)


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
        stock = float(self.stock)
        min_stock = float(self.min_stock)
        if stock <= min_stock * 0.4:
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
    STATUS = [("active", "Activa"), ("draft", "Borrador"), ("archived", "Archivada")]
    DIFFICULTY = [("easy", "Fácil"), ("medium", "Media"), ("hard", "Difícil")]

    name = models.CharField(max_length=120)
    emoji = models.TextField(default="🍽️")
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, blank=True)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="recipes")
    station = models.CharField(max_length=12, choices=STATION, default="grill")
    status = models.CharField(max_length=12, choices=STATUS, default="draft")
    difficulty = models.CharField(max_length=12, choices=DIFFICULTY, default="easy")
    portions = models.PositiveIntegerField(default=1)
    prep_minutes = models.PositiveIntegerField(default=10)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    variations = models.JSONField(default=list)
    steps = models.JSONField(default=list)
    allergens = models.JSONField(default=list)
    allergens_other = models.CharField(max_length=200, blank=True)
    tags = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ingredients")
    item = models.ForeignKey(InventoryItem, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=120, blank=True)
    unit = models.CharField(max_length=16, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    waste = models.FloatField(default=0)  # 0..1


class Table(TenantScoped):
    STATUS = [("available", "Disponible"), ("occupied", "Ocupada"), ("reserved", "Reservada"), ("billing", "Cuenta")]
    SHAPE = [("round", "Redonda"), ("square", "Cuadrada"), ("rect", "Rectangular")]
    number = models.PositiveIntegerField()
    capacity = models.PositiveIntegerField(default=4)
    zone = models.CharField(max_length=60, default="Salón")
    status = models.CharField(max_length=12, choices=STATUS, default="available")
    waiter = models.CharField(max_length=80, blank=True)
    seated_at = models.DateTimeField(null=True, blank=True)
    x = models.FloatField(default=50)
    y = models.FloatField(default=50)
    shape = models.CharField(max_length=10, choices=SHAPE, default="square")


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
    # Idempotencia del descuento de inventario: el stock se descuenta una sola
    # vez, cuando la cocina pasa la orden a "preparing"/"ready". Nunca al cobrar.
    stock_consumed = models.BooleanField(default=False)


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    notes = models.CharField(max_length=200, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)


class OrderChangeLog(TenantScoped):
    """Auditoría de ediciones a una orden ya enviada (backlog #4)."""
    ACTION = [("edit", "Edición"), ("add", "Agregar"), ("remove", "Eliminar"), ("status", "Cambio de estado")]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="change_logs")
    action = models.CharField(max_length=12, choices=ACTION, default="edit")
    user = models.CharField(max_length=80, blank=True)
    summary = models.CharField(max_length=200, blank=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


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


# ─── Proveedores ──────────────────────────────────────────────────────────────

class Supplier(TenantScoped):
    name = models.CharField(max_length=120)
    contact = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    category = models.CharField(max_length=40, default="Abarrotes")
    nit = models.CharField(max_length=30, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Purchase(TenantScoped):
    code = models.CharField(max_length=20)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    date = models.DateField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    invoice_photo = models.TextField(blank=True)  # base64 data URL

    def __str__(self):
        return self.code


class PurchaseLine(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)  # costo antes de IVA
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # % IVA/impuesto de esta línea
    unit = models.CharField(max_length=16, blank=True)


# ─── Reservaciones ───────────────────────────────────────────────────────────

class Reservation(TenantScoped):
    STATUS = [
        ("pending", "Pendiente"), ("confirmed", "Confirmada"),
        ("arrived", "Llegó"), ("cancelled", "Cancelada"),
    ]
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, blank=True)
    table_number = models.PositiveIntegerField(default=1)
    date = models.DateField()
    time = models.TimeField()
    guests = models.PositiveIntegerField(default=2)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} {self.date} {self.time}"


# ─── Empleados ───────────────────────────────────────────────────────────────

class Employee(TenantScoped):
    ROLE = [
        ("mesero", "Mesero"),
        ("cocinero", "Cocinero"),
        ("cajero", "Cajero"),
        ("admin", "Administrador"),
        ("almacen", "Almacén"),
    ]
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=16, choices=ROLE, default="mesero")
    active = models.BooleanField(default=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)

    def __str__(self):
        return self.name


# ─── Ventas (registro POS) ───────────────────────────────────────────────────

class Sale(TenantScoped):
    """Registro de ventas completadas desde el POS."""
    METHODS = [
        ("card", "Tarjeta"), ("cash", "Efectivo"),
        ("transfer", "Transferencia"), ("nequi", "Nequi"),
    ]
    total = models.DecimalField(max_digits=14, decimal_places=2)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    items = models.PositiveIntegerField(default=0)
    method = models.CharField(max_length=20, choices=METHODS, default="cash")
    sale_type = models.CharField(max_length=80, blank=True)
    table_number = models.PositiveIntegerField(null=True, blank=True)
    tip = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    waiter = models.CharField(max_length=80, blank=True)
    customer = models.CharField(max_length=120, blank=True)
    observations = models.CharField(max_length=300, blank=True)
    # Número de factura correlativo por tenant (backlog #1).
    invoice_number = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Venta {self.id} ${self.total}"


# ─── Devoluciones (Notas de Crédito) ──────────────────────────────────────────

class CreditNote(TenantScoped):
    """Nota de crédito por devolución de una venta o producto (backlog #6)."""
    code = models.CharField(max_length=24)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_notes")
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    method = models.CharField(max_length=20, default="cash")
    reason = models.CharField(max_length=300)  # motivo obligatorio
    user = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"NC {self.code}"


class CreditNoteLine(models.Model):
    note = models.ForeignKey(CreditNote, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    restocked = models.BooleanField(default=False)


# ─── WhatsApp ───────────────────────────────────────────────────────────────

class WhatsAppCustomer(TenantScoped):
    phone = models.CharField(max_length=30, db_index=True)
    name = models.CharField(max_length=120, default="Cliente")
    address = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    order_count = models.PositiveIntegerField(default=0)
    last_order_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tenant", "phone")

    def __str__(self):
        return f"{self.name} ({self.phone})"


class WhatsAppOrder(TenantScoped):
    STATUS = [
        ("review", "Por verificar"), ("verified", "Verificado"),
        ("dispatched", "Despachado"), ("rejected", "Rechazado"),
    ]
    code = models.CharField(max_length=16)
    wa_customer = models.ForeignKey(WhatsAppCustomer, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    customer_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=STATUS, default="review")
    receipt_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"WA {self.code} - {self.customer_name}"


class WhatsAppOrderLine(models.Model):
    order = models.ForeignKey(WhatsAppOrder, on_delete=models.CASCADE, related_name="lines")
    name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2)


class WhatsAppConfig(TenantScoped):
    twilio_sid = models.CharField(max_length=60, blank=True)
    twilio_token = models.CharField(max_length=60, blank=True)
    twilio_whatsapp_number = models.CharField(max_length=30, blank=True)
    glm_api_key = models.CharField(max_length=120, blank=True)
    glm_model = models.CharField(max_length=40, default="glm-4.5-flash")
    glm_base_url = models.URLField(default="https://open.bigmodel.cn/api/paas/v4")
    enabled = models.BooleanField(default=False)
    greeting = models.TextField(blank=True)
    restaurant_name = models.CharField(max_length=120, blank=True)
    menu_text = models.TextField(blank=True)
    payment_info = models.TextField(blank=True)
    business_info = models.TextField(blank=True)
    menu_pdf = models.FileField(upload_to="whatsapp/menus/", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "WhatsApp configs"

    def __str__(self):
        return f"WA Config - {self.restaurant_name}"
