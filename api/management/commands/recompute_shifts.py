"""
Recalcula los cierres de turno a partir de las ventas reales.

Hasta el 14 de septiembre de 2026 la caja cargaba TODAS las ventas del
restaurante, así que cada cierre guardó el acumulado histórico en vez de lo
vendido en su turno. Aquí cada cierre se reconstruye con las ventas de su
ventana: desde el cierre anterior (o desde siempre, para el primero) hasta su
propia hora de cierre. Las ventas anuladas ya no existen, así que dejan de
contar solas.

    python manage.py recompute_shifts            # solo muestra qué cambiaría
    python manage.py recompute_shifts --apply    # escribe
    python manage.py recompute_shifts --tenant cusper-bar --apply
"""
import json
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from rest_framework.renderers import JSONRenderer

from api import models, serializers


def snapshot(sale):
    """Venta como la guarda el cliente en el cierre (mismo JSON del API)."""
    return json.loads(JSONRenderer().render(serializers.SaleSerializer(sale).data))


class Command(BaseCommand):
    help = "Recalcula totales y detalle de cada cierre de turno con las ventas de su ventana."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Escribe los cambios (sin esto es simulación).")
        parser.add_argument("--tenant", help="Slug de un solo restaurante.")

    def handle(self, *args, **opts):
        closes = models.ShiftClose.objects.select_related("tenant").order_by("tenant_id", "created_at", "id")
        if opts.get("tenant"):
            closes = closes.filter(tenant__slug=opts["tenant"])

        by_tenant = defaultdict(list)
        for sc in closes:
            by_tenant[sc.tenant].append(sc)

        changed = 0
        with transaction.atomic():
            for tenant, items in by_tenant.items():
                self.stdout.write(self.style.MIGRATE_HEADING(f"\n{tenant.name} ({tenant.slug})"))
                prev = None
                for i, sc in enumerate(items, start=1):
                    qs = models.Sale.objects.filter(tenant=tenant, created_at__lte=sc.created_at)
                    if prev is not None:
                        qs = qs.filter(created_at__gt=prev.created_at)
                    sales = list(qs.prefetch_related("orders__lines__product").order_by("-created_at"))

                    total = sum(float(s.total) for s in sales)
                    tips = sum(float(s.tip or 0) for s in sales)
                    by_method, by_waiter = defaultdict(float), defaultdict(float)
                    for s in sales:
                        by_method[s.method] += float(s.total) - float(s.tip or 0)
                        if s.tip:
                            by_waiter[s.waiter or "Sin asignar"] += float(s.tip)
                    orders = len(sales)
                    avg = round(total / orders) if orders else 0

                    if prev is not None:
                        started = prev.created_at
                    else:
                        first = qs.order_by("created_at").first()
                        started = first.created_at if first else sc.created_at

                    old = (float(sc.sales_total), sc.orders)
                    flag = "" if old == (round(total, 2), orders) else "  <- cambia"
                    self.stdout.write(
                        f"  Turno #{i} {sc.created_at:%Y-%m-%d %H:%M}: "
                        f"antes ${old[0]:,.0f} / {old[1]} ventas -> ahora ${total:,.0f} / {orders} ventas{flag}"
                    )

                    sc.number = i
                    sc.started_at = started
                    sc.sales_total = round(total, 2)
                    sc.orders = orders
                    sc.avg_ticket = avg
                    sc.total_tips = round(tips, 2)
                    sc.by_method = {k: round(v, 2) for k, v in by_method.items()}
                    sc.by_waiter = {k: round(v, 2) for k, v in by_waiter.items()}
                    sc.records = [snapshot(s) for s in sales]
                    if opts["apply"]:
                        sc.save()
                    changed += bool(flag)
                    prev = sc

            if not opts["apply"]:
                self.stdout.write(self.style.WARNING(f"\nSimulación: {changed} cierre(s) cambiarían. Usa --apply para escribir."))
                transaction.set_rollback(True)
            else:
                self.stdout.write(self.style.SUCCESS(f"\nListo: {changed} cierre(s) corregidos."))
