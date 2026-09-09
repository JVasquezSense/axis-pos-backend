from django.db import migrations


def backfill(apps, schema_editor):
    """
    Marca como "requiere insumos" lo que ya tiene ficha técnica.

    El campo nace con `simple` por defecto; sin esta pasada, todos los platos
    preparados que existen quedarían marcados como si fueran un insumo suelto y
    dejarían de descontar sus ingredientes.
    """
    Product = apps.get_model("api", "Product")
    Recipe = apps.get_model("api", "Recipe")

    with_recipe = set(
        Recipe.objects.filter(product__isnull=False).values_list("product_id", flat=True)
    )
    updated = Product.objects.filter(id__in=with_recipe).update(kind="compound")
    print(f"  productos marcados como 'requiere insumos': {updated}")


def undo(apps, schema_editor):
    apps.get_model("api", "Product").objects.update(kind="simple")


class Migration(migrations.Migration):
    dependencies = [("api", "0030_product_kind")]
    operations = [migrations.RunPython(backfill, undo)]
