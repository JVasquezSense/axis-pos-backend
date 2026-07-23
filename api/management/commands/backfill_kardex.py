"""
Backfill del kardex: garantiza que todo InventoryItem tenga un movimiento
"inicial" con balance = stock actual, de forma idempotente.

Uso:
    python manage.py backfill_kardex

Contexto: antes de esta versión, crear un insumo NO generaba su movimiento
inicial, por lo que el saldo inicial del kardex aparecía en 0. Este comando
repara el histórico para todos los tenants sin alterar el stock actual ni
los movimientos válidos ya registrados.
"""
from django.core.management.base import BaseCommand
from api import models


class Command(BaseCommand):
    help = "Crea el movimiento 'inicial' del kardex para insumos que no lo tengan."

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        items = models.InventoryItem.objects.all().order_by("id")
        for item in items:
            # Idempotente: si ya existe un movimiento inicial, no hacemos nada.
            ya_tiene = item.movements.filter(type="inicial").exists()
            if ya_tiene:
                skipped += 1
                continue
            models.InventoryMovement.objects.create(
                tenant=item.tenant,
                item=item,
                type="inicial",
                quantity=item.stock,
                balance=item.stock,
                unit_cost=item.cost,
                reason=f"Saldo inicial (backfill) · {item.name}",
            )
            created += 1
        self.stdout.write(self.style.SUCCESS(
            f"Kardex reparado: {created} movimientos iniciales creados, {skipped} saltados (ya existían)."
        ))
