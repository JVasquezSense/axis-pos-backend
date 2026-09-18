import re

import django.db.models.deletion
from django.db import migrations, models


ORDER_CODE = re.compile(r"Orden\s+(\S+)")


def link_orders(apps, schema_editor):
    """
    Recupera el pedido de los movimientos ya guardados.

    Hasta ahora el único rastro del origen era el texto de `reason`
    ("Venta · Orden OC-ABC123"). Enlazarlos deja que el kardex muestre mesa,
    mesero y número de factura también en el histórico, no solo en lo nuevo.
    """
    InventoryMovement = apps.get_model("api", "InventoryMovement")
    Order = apps.get_model("api", "Order")

    pending = InventoryMovement.objects.filter(order__isnull=True, reason__contains="Orden")
    by_tenant = {}
    updates = []
    for mv in pending.iterator():
        match = ORDER_CODE.search(mv.reason or "")
        if not match:
            continue
        codes = by_tenant.get(mv.tenant_id)
        if codes is None:
            codes = dict(
                Order.objects.filter(tenant_id=mv.tenant_id).values_list("code", "id")
            )
            by_tenant[mv.tenant_id] = codes
        order_id = codes.get(match.group(1))
        if order_id is not None:
            mv.order_id = order_id
            updates.append(mv)

    # bulk_update recibe el nombre del campo ("order"), no su columna ("order_id").
    for i in range(0, len(updates), 500):
        InventoryMovement.objects.bulk_update(updates[i:i + 500], ["order"])


class Migration(migrations.Migration):
    dependencies = [("api", "0047_inventorymovement_table_waiter")]
    operations = [
        migrations.AddField(
            "inventorymovement",
            "order",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="inventory_movements",
                to="api.order",
            ),
        ),
        migrations.RunPython(link_orders, migrations.RunPython.noop),
    ]
