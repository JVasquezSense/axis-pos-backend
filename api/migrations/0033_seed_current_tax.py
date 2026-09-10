from django.db import migrations

# Lo que el código venía cobrando fijo a todo el mundo.
LEGACY_RATE = 8


def seed(apps, schema_editor):
    """
    Cada restaurante arranca con el impuesto que ya se le estaba aplicando.

    El 8% estaba escrito en el código: si el catálogo naciera vacío, todas las
    cuentas dejarían de cobrarlo de un día para otro sin que nadie lo decidiera.
    Queda como un impuesto normal del restaurante, que ahora sí puede editar,
    renombrar o borrar.
    """
    Tenant = apps.get_model("api", "Tenant")
    Tax = apps.get_model("api", "Tax")
    for tenant in Tenant.objects.all():
        if Tax.objects.filter(tenant=tenant).exists():
            continue
        Tax.objects.create(
            tenant=tenant, name="IVA", type="percent", rate=LEGACY_RATE,
            is_default=True, active=True,
        )


def unseed(apps, schema_editor):
    apps.get_model("api", "Tax").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0032_tax")]
    operations = [migrations.RunPython(seed, unseed)]
