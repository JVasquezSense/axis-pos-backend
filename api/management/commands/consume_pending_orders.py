"""
Descuenta el inventario de los pedidos que ya se sirvieron pero nunca lo movieron.

El 18 de septiembre de 2026, entre las 18:08 y las 18:50 (hora de Colombia),
`consume_order_inventory` fallaba al bloquear la fila del pedido
(select_for_update sobre un outer join) y el error caía en un `except` que lo
silenciaba: los pedidos se cerraban normal pero el kardex no recibía ni un
movimiento. Esos pedidos quedaron con `stock_consumed=False`, así que nadie los
vuelve a descontar solo: ya pasaron por "ready" y no habrá otro PATCH.

Este comando los busca y los descuenta con la misma función de siempre, que es
idempotente: un pedido ya descontado se salta solo.

    python manage.py consume_pending_orders --since 2026-09-18T18:00
    python manage.py consume_pending_orders --since 2026-09-18T18:00 --apply
    python manage.py consume_pending_orders --since ... --tenant cusper-bar --apply
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api import models
from api.views import consume_order_inventory


class Command(BaseCommand):
    help = "Descuenta el inventario de los pedidos servidos que quedaron sin mover el kardex."

    def add_arguments(self, parser):
        parser.add_argument("--since", required=True, help="Desde cuándo mirar: YYYY-MM-DD o YYYY-MM-DDTHH:MM")
        parser.add_argument("--until", help="Hasta cuándo (opcional), mismo formato.")
        parser.add_argument("--tenant", help="Slug de un solo restaurante; sin esto, todos.")
        parser.add_argument("--apply", action="store_true", help="Escribe los cambios (sin esto es simulación).")

    def parse(self, value):
        return timezone.make_aware(datetime.fromisoformat(value)) if value else None

    def handle(self, *args, **opts):
        since = self.parse(opts["since"])
        until = self.parse(opts.get("until"))

        # Solo lo que ya se entregó: un pedido todavía pendiente descuenta solo
        # cuando la cocina lo marque, y adelantarlo lo descontaría dos veces.
        orders = (
            models.Order.objects
            .filter(stock_consumed=False, status__in=("ready", "served", "paid"), created_at__gte=since)
            .exclude(status="cancelled")
            .select_related("tenant")
            .order_by("created_at")
        )
        if until:
            orders = orders.filter(created_at__lte=until)
        if opts.get("tenant"):
            orders = orders.filter(tenant__slug=opts["tenant"])

        orders = list(orders)
        if not orders:
            self.stdout.write(self.style.SUCCESS("No hay pedidos pendientes de descontar."))
            return

        done = 0
        for order in orders:
            self.stdout.write(
                f"  {order.tenant.slug} · {order.code} · {order.created_at:%m-%d %H:%M} · {order.status}"
            )
            if not opts["apply"]:
                continue
            try:
                with transaction.atomic():
                    consume_order_inventory(order)
                done += 1
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"    falló: {exc}"))

        if opts["apply"]:
            self.stdout.write(self.style.SUCCESS(f"\nDescontados {done} de {len(orders)} pedidos."))
        else:
            self.stdout.write(
                self.style.WARNING(f"\nSimulación: {len(orders)} pedido(s) se descontarían. Usa --apply para escribir.")
            )
