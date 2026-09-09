import unicodedata

from django.db import migrations

# Cuántas palabras de más se toleran, y siempre AL PRINCIPIO.
MAX_EXTRA_WORDS = 2


def normalize(name):
    text = unicodedata.normalize("NFD", (name or "").strip().lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.split())


def same_thing(product_name, item_name):
    """
    ¿Producto e insumo son la misma cosa?

    Igual nombre, o uno es el otro con una palabra de categoría delante: el
    inventario dice "Cigarrillo Lucky Strike Alaska" y la carta "Lucky Strike
    Alaska". Solo cuenta lo que sobra AL PRINCIPIO: lo que difiere al final
    distingue variantes ("Coca Cola" no es "Coca Cola Zero") y confundirlas
    descontaría del insumo equivocado.
    """
    if product_name == item_name:
        return True
    short, long = sorted((product_name, item_name), key=len)
    # Con una sola palabra en común la coincidencia no dice nada: "Pollo" cabe
    # dentro de "Pechuga de pollo" y no son lo mismo.
    if len(short.split()) < 2 or not long.endswith(short):
        return False
    prefix = long[: len(long) - len(short)].split()
    return 0 < len(prefix) <= MAX_EXTRA_WORDS


def link(apps, schema_editor):
    """
    Segunda pasada del enlace producto → insumo.

    La primera exigía nombres idénticos y no enlazó nada: en la práctica el
    insumo se llama "Cigarrillo Lucky Strike Alaska" y el producto "Lucky Strike
    Alaska". Se enlaza solo cuando la coincidencia es única.
    """
    Product = apps.get_model("api", "Product")
    InventoryItem = apps.get_model("api", "InventoryItem")
    Recipe = apps.get_model("api", "Recipe")

    with_recipe = set(
        Recipe.objects.filter(product__isnull=False).values_list("product_id", flat=True)
    )

    items_by_tenant = {}
    for item in InventoryItem.objects.all():
        items_by_tenant.setdefault(item.tenant_id, []).append((normalize(item.name), item.id))

    linked = 0
    for product in Product.objects.filter(inventory_item__isnull=True, is_combo=False):
        if product.id in with_recipe:
            continue
        name = normalize(product.name)
        candidates = items_by_tenant.get(product.tenant_id, [])
        exact = [item_id for item_name, item_id in candidates if item_name == name]
        matches = exact or [
            item_id for item_name, item_id in candidates if same_thing(name, item_name)
        ]
        # Varias opciones: no se adivina, se vincula a mano desde el producto.
        if len(matches) != 1:
            continue
        product.inventory_item_id = matches[0]
        product.save(update_fields=["inventory_item"])
        linked += 1
    print(f"  productos vinculados a su insumo: {linked}")


class Migration(migrations.Migration):
    dependencies = [("api", "0028_seed_mini_plan")]
    operations = [migrations.RunPython(link, migrations.RunPython.noop)]
