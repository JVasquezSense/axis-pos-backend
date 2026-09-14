from django.db import migrations


def backfill(apps, schema_editor):
    """Numera los cierres existentes por restaurante y les pone su inicio."""
    ShiftClose = apps.get_model("api", "ShiftClose")
    Sale = apps.get_model("api", "Sale")
    tenants = ShiftClose.objects.values_list("tenant_id", flat=True).distinct()
    for tenant_id in tenants:
        prev = None
        for i, sc in enumerate(ShiftClose.objects.filter(tenant_id=tenant_id).order_by("created_at", "id"), start=1):
            if prev is None:
                first_sale = Sale.objects.filter(tenant_id=tenant_id).order_by("created_at").first()
                started = first_sale.created_at if first_sale else sc.created_at
            else:
                started = prev.created_at
            sc.number = i
            sc.started_at = started
            sc.save(update_fields=["number", "started_at"])
            prev = sc


class Migration(migrations.Migration):
    dependencies = [("api", "0040_shift_number")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
