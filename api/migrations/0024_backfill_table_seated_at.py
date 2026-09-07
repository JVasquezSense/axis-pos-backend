from django.db import migrations
from django.utils import timezone

ACTIVE = ["pending", "preparing", "ready", "served"]


def backfill(apps, schema_editor):
    """
    Mesas ocupadas sin hora de sentada: el tiempo de espera solo se guardaba
    cuando había un cambio de estado, así que las que se ocuparon por otro
    camino quedaron sin reloj en el mapa del salón. Se recupera desde su pedido
    activo más antiguo; si ya no hay ninguno, la mesa se libera.
    """
    Table = apps.get_model("api", "Table")
    Order = apps.get_model("api", "Order")
    now = timezone.now()

    for table in Table.objects.filter(status__in=["occupied", "billing"], seated_at__isnull=True):
        started = (
            Order.objects.filter(table_id=table.id, status__in=ACTIVE)
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        if started:
            table.seated_at = started
            table.save(update_fields=["seated_at"])
        else:
            table.status = "available"
            table.save(update_fields=["status"])


class Migration(migrations.Migration):
    dependencies = [("api", "0023_salonzone")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
