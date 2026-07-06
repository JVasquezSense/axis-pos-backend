"""
Carga datos iniciales para tener la API operativa tras el despliegue.
Uso: python manage.py seed
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from api import models

# Credenciales del usuario demo (cámbialas en producción)
DEMO_EMAIL = "admin@axispos.co"
DEMO_PASSWORD = "Axis2026!"


class Command(BaseCommand):
    help = "Crea un usuario demo y un restaurante con categorías, productos e inventario."

    def handle(self, *args, **options):
        # Usuario para iniciar sesión desde el frontend
        User = get_user_model()
        if not User.objects.filter(username=DEMO_EMAIL).exists():
            User.objects.create_superuser(username=DEMO_EMAIL, email=DEMO_EMAIL, password=DEMO_PASSWORD)
            self.stdout.write(self.style.SUCCESS(f"Usuario demo creado: {DEMO_EMAIL} / {DEMO_PASSWORD}"))
        else:
            self.stdout.write(self.style.WARNING(f"El usuario {DEMO_EMAIL} ya existe."))

        tenant, created = models.Tenant.objects.get_or_create(
            name="Demo Burger",
            defaults={"slug": "demo-burger", "logo": "🍔", "plan": "growth", "status": "active", "city": "Medellín"},
        )
        if not created:
            self.stdout.write(self.style.WARNING("El restaurante demo ya existe."))
            return

        cats = {}
        for name, icon in [("Hamburguesas", "Beef"), ("Bebidas", "CupSoda"), ("Postres", "IceCream")]:
            cats[name] = models.Category.objects.create(tenant=tenant, name=name, icon=icon)

        products = [
            ("Axis Classic", "Hamburguesas", 27900, "🍔", True),
            ("Doble Bacon", "Hamburguesas", 36900, "🥓", True),
            ("Limonada de Coco", "Bebidas", 12900, "🥥", True),
            ("Brownie con Helado", "Postres", 16900, "🍫", False),
        ]
        for name, cat, price, emoji, popular in products:
            models.Product.objects.create(
                tenant=tenant, name=name, category=cats[cat], price=price, image=emoji, popular=popular,
            )

        inventory = [
            ("Carne de res molida", "Carnes", 2.1, "kg", 8, 28000),
            ("Pan de hamburguesa", "Panadería", 34, "und", 40, 1200),
            ("Queso cheddar", "Lácteos", 1.8, "kg", 5, 32000),
        ]
        for name, cat, stock, unit, mins, cost in inventory:
            item = models.InventoryItem(
                tenant=tenant, name=name, category=cat, stock=stock, unit=unit, min_stock=mins, cost=cost,
            )
            item.recompute_status()
            item.save()

        self.stdout.write(self.style.SUCCESS("Datos demo creados para 'Demo Burger'."))
