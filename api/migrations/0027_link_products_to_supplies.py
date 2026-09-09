import unicodedata

from django.db import migrations


def normalize(name):
    text = unicodedata.normalize("NFD", (name or "").strip().lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.split())


def link(apps, schema_editor):
    """
    Vincula cada producto con el insumo que se llama igual.

    Los productos que SON un insumo (una cerveza, una cajetilla de cigarrillos)
    se vendían sin mover el kardex: descontar exigía montarles una ficha técnica
    de un solo ingrediente y nadie lo hacía. Solo se enlaza cuando el nombre
    coincide exactamente y no hay ambigüedad; el resto se vincula a mano.
    """
    Product = apps.get_model("api", "Product")
    InventoryItem = apps.get_model("api", "InventoryItem")
    Recipe = apps.get_model("api", "Recipe")

    with_recipe = set(
        Recipe.objects.filter(product__isnull=False).values_list("product_id", flat=True)
    )

    by_tenant = {}
    for item in InventoryItem.objects.all():
        key = normalize(item.name)
        bucket = by_tenant.setdefault(item.tenant_id, {})
        # Nombre repetido dentro del restaurante: ambiguo, no se adivina.
        bucket[key] = None if key in bucket else item.id

    linked = 0
    for product in Product.objects.filter(inventory_item__isnull=True, is_combo=False):
        if product.id in with_recipe:
            continue
        item_id = by_tenant.get(product.tenant_id, {}).get(normalize(product.name))
        if not item_id:
            continue
        product.inventory_item_id = item_id
        product.save(update_fields=["inventory_item"])
        linked += 1
    print(f"  productos vinculados a su insumo: {linked}")


class Migration(migrations.Migration):
    dependencies = [("api", "0026_plan_mini")]
    operations = [migrations.RunPython(link, migrations.RunPython.noop)]
