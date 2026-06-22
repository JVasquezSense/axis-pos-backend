"""
Carga datos iniciales para tener la API operativa tras el despliegue.
Uso: python manage.py seed
"""
from django.core.management.base import BaseCommand
from api import models


class Command(BaseCommand):
    help = "Crea un restaurante demo con categorías, productos e inventario."

    def handle(self, *args, **options):
        tenant, created = models.Tenant.objects.get_or_create(
            name="Demo Burger",
            defaults={"logo": "🍔", "plan": "growth", "status": "active", "city": "Medellín"},
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
