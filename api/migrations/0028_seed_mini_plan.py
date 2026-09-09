from django.db import migrations

# Lo justo para vender: salón, pedidos, cocina, caja, cierre de turno,
# productos, empleados e inventario. Sin fichas técnicas.
MINI = {
    "dashboard": True, "salon": True, "orders": True, "kitchen": True, "checkout": True,
    "shift": True, "menu": True, "employees": True, "inventory": True,
    "reservations": False, "history": False, "returns": False, "shift-history": False,
    "weborders": False, "suppliers": False, "audit": False, "crm": False,
    "reports": False, "delivery": False, "delivery-admin": False, "website": False,
    "qr": False, "whatsapp": False, "voice": False,
    "ai": True,
    "recipes": False,
    "max_users": 3,
}


def seed(apps, schema_editor):
    Plan = apps.get_model("api", "Plan")
    Plan.objects.update_or_create(
        code="mini",
        defaults={"name": "Axis Mini", "max_users": 3, "price": 0, "features": MINI},
    )
    # Los planes que ya existen conservan las fichas técnicas: sin la clave,
    # heredarían el `False` del plan Mini al leerse el catálogo.
    for plan in Plan.objects.exclude(code="mini"):
        features = dict(plan.features or {})
        features.setdefault("recipes", True)
        plan.features = features
        plan.save(update_fields=["features"])


def unseed(apps, schema_editor):
    apps.get_model("api", "Plan").objects.filter(code="mini").delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0027_link_products_to_supplies")]
    operations = [migrations.RunPython(seed, unseed)]
