import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("logo", models.CharField(default="🍔", max_length=8)),
                ("plan", models.CharField(choices=[("starter", "Starter"), ("growth", "Growth"), ("enterprise", "Enterprise")], default="starter", max_length=20)),
                ("status", models.CharField(choices=[("active", "Activo"), ("trial", "Prueba"), ("past_due", "Mora"), ("churned", "Cancelado")], default="trial", max_length=20)),
                ("city", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("icon", models.CharField(default="Utensils", max_length=40)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="categorys", to="api.tenant")),
            ],
            options={"verbose_name_plural": "categories"},
        ),
        migrations.CreateModel(
            name="InventoryItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("category", models.CharField(max_length=80)),
                ("stock", models.DecimalField(decimal_places=3, max_digits=12)),
                ("unit", models.CharField(max_length=16)),
                ("min_stock", models.DecimalField(decimal_places=3, max_digits=12)),
                ("cost", models.DecimalField(decimal_places=2, max_digits=12)),
                ("supplier", models.CharField(blank=True, max_length=120)),
                ("status", models.CharField(choices=[("normal", "Normal"), ("low", "Bajo"), ("critical", "Crítico")], default="normal", max_length=12)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventoryitems", to="api.tenant")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("image", models.CharField(default="🍽️", max_length=8)),
                ("tags", models.JSONField(default=list)),
                ("available", models.BooleanField(default=True)),
                ("prep_minutes", models.PositiveIntegerField(default=10)),
                ("popular", models.BooleanField(default=False)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="products", to="api.category")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="products", to="api.tenant")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="Recipe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("emoji", models.CharField(default="🍽️", max_length=8)),
                ("station", models.CharField(choices=[("grill", "Parrilla"), ("fry", "Freidora"), ("cold", "Fríos"), ("bar", "Barra"), ("pastry", "Pastelería")], default="grill", max_length=12)),
                ("portions", models.PositiveIntegerField(default=1)),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recipes", to="api.product")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recipes", to="api.tenant")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="RecipeIngredient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12)),
                ("waste", models.FloatField(default=0)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="api.inventoryitem")),
                ("recipe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ingredients", to="api.recipe")),
            ],
        ),
        migrations.CreateModel(
            name="Table",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField()),
                ("capacity", models.PositiveIntegerField(default=4)),
                ("zone", models.CharField(default="Salón", max_length=60)),
                ("status", models.CharField(choices=[("available", "Disponible"), ("occupied", "Ocupada"), ("reserved", "Reservada"), ("billing", "Cuenta")], default="available", max_length=12)),
                ("waiter", models.CharField(blank=True, max_length=80)),
                ("seated_at", models.DateTimeField(blank=True, null=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tables", to="api.tenant")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=16)),
                ("channel", models.CharField(choices=[("dine_in", "Mesa"), ("takeaway", "Para llevar"), ("delivery", "Domicilio"), ("web", "Web")], default="dine_in", max_length=12)),
                ("status", models.CharField(choices=[("pending", "Pendiente"), ("preparing", "Preparando"), ("ready", "Listo"), ("served", "Servido"), ("paid", "Pagado")], default="pending", max_length=12)),
                ("customer", models.CharField(blank=True, max_length=120)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("receipt", models.FileField(blank=True, null=True, upload_to="receipts/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("table", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="orders", to="api.table")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="orders", to="api.tenant")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="OrderLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="api.order")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="api.product")),
            ],
        ),
        migrations.CreateModel(
            name="InventoryMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(choices=[("inicial", "Inicial"), ("entrada", "Entrada"), ("salida", "Salida"), ("ajuste", "Ajuste")], max_length=12)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12)),
                ("balance", models.DecimalField(decimal_places=3, max_digits=12)),
                ("unit_cost", models.DecimalField(decimal_places=2, max_digits=12)),
                ("reason", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="movements", to="api.inventoryitem")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventorymovements", to="api.tenant")),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("phone", models.CharField(max_length=30)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("total_spent", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("visits", models.PositiveIntegerField(default=0)),
                ("points", models.PositiveIntegerField(default=0)),
                ("tier", models.CharField(choices=[("bronze", "Bronce"), ("silver", "Plata"), ("gold", "Oro"), ("platinum", "Platino")], default="bronze", max_length=12)),
                ("last_visit", models.DateField(blank=True, null=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="customers", to="api.tenant")),
            ],
            options={"abstract": False},
        ),
    ]
