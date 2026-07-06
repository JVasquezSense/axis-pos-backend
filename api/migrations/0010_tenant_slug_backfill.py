# Rellena slug para tenants existentes (creados antes de 0009) y luego aplica
# la restricción de unicidad. Separado de 0009 porque mezclar un AddField
# (cambio de esquema) con un RunPython (datos) en la misma migración rompe
# en SQLite, que reconstruye la tabla completa para alterar columnas.

from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    Tenant = apps.get_model("api", "Tenant")
    used = set(Tenant.objects.exclude(slug="").values_list("slug", flat=True))
    # Materializa antes de actualizar: iterar y escribir sobre el mismo
    # queryset perezoso puede releer filas ya modificadas (visto en SQLite).
    blanks = list(Tenant.objects.filter(slug="").only("pk", "name"))
    for tenant in blanks:
        base = slugify(tenant.name)[:140] or "restaurante"
        candidate = base
        i = 2
        while candidate in used:
            candidate = f"{base}-{i}"[:140]
            i += 1
        used.add(candidate)
        Tenant.objects.filter(pk=tenant.pk).update(slug=candidate)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_tenant_slug'),
    ]

    operations = [
        migrations.RunPython(populate_slugs, noop),
        migrations.AlterField(
            model_name='tenant',
            name='slug',
            field=models.SlugField(blank=True, max_length=140, unique=True),
        ),
    ]
