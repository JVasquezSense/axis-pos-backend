"""
Cuadra el kardex con lo realmente vendido.

Para cada pedido que ya descontó inventario, compara lo que sus líneas
actuales exigen (con los vínculos producto→insumo de hoy) contra los
movimientos que ese pedido dejó en el kardex, y mueve la diferencia. Sirve
para dos fallas ya corregidas en el código: pedidos editados después del
primer descuento y productos que no tenían insumo vinculado al venderse.

Un insumo con conteo físico posterior al pedido no se toca por ese pedido:
el conteo ya dejó el saldo real.

    python manage.py reconcile_orders --tenant cusper-bar --since 2026-09-11
    python manage.py reconcile_orders --tenant cusper-bar --since 2026-09-11 --apply
"""
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from api import models
from api.views import broadcast_inventory, consume_recipe_demand, expand_products


class Command(BaseCommand):
    help = "Mueve en el kardex la diferencia entre lo vendido y lo descontado por pedido."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument("--since", required=True, help="YYYY-MM-DD")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        tenant = models.Tenant.objects.get(slug=opts["tenant"])
        since = timezone.make_aware(timezone.datetime.combine(date.fromisoformat(opts["since"]), timezone.datetime.min.time()))
        last_count = {
            r["item_id"]: r["at"]
            for r in models.InventoryMovement.objects.filter(tenant=tenant, reason__icontains="conteo")
            .values("item_id").annotate(at=Max("created_at"))
        }
        orders = (models.Order.objects.filter(tenant=tenant, stock_consumed=True, created_at__gte=since)
                  .exclude(status="cancelled").prefetch_related("lines__product").order_by("created_at"))

        total_more, total_less = defaultdict(float), defaultdict(float)
        touched_all, moves_all = [], []
        with transaction.atomic():
            for order in orders:
                demand = expand_products((ln.product, ln.quantity) for ln in order.lines.all())
                # Lo que el pedido exige, en insumos.
                expected = self.demand_to_items(tenant, demand)
                moved = defaultdict(float)
                for m in models.InventoryMovement.objects.filter(tenant=tenant, reason__endswith=f"Orden {order.code}"):
                    moved[m.item_id] += float(-m.quantity)
                diff = {}
                for item_id in set(expected) | set(moved):
                    if item_id in last_count and last_count[item_id] >= order.created_at:
                        continue  # el conteo físico ya fijó este insumo
                    d = round(expected.get(item_id, 0.0) - moved.get(item_id, 0.0), 3)
                    if abs(d) >= 0.0005:
                        diff[item_id] = d
                if not diff:
                    continue
                names = {it.id: it.name for it in models.InventoryItem.objects.filter(id__in=diff.keys())}
                self.stdout.write(f"{order.code} {order.created_at:%m-%d %H:%M}: " + ", ".join(
                    f"{names[i]} {'+' if d > 0 else ''}{-d:g}" for i, d in diff.items()))
                for i, d in diff.items():
                    (total_more if d > 0 else total_less)[names[i]] += abs(d)
                if opts["apply"]:
                    # consume_recipe_demand trabaja por producto; aquí ya está en
                    # insumos, así que se escribe el movimiento directo.
                    for item_id, d in diff.items():
                        item = models.InventoryItem.objects.select_for_update().get(pk=item_id)
                        item.stock = float(item.stock) - d
                        item.recompute_status()
                        item.save()
                        mv = models.InventoryMovement.objects.create(
                            tenant=tenant, item=item, type="salida" if d > 0 else "ajuste",
                            quantity=-d, balance=item.stock, unit_cost=item.cost,
                            reason=f"Cuadre · Orden {order.code}",
                        )
                        touched_all.append(item); moves_all.append(mv)
            if not opts["apply"]:
                transaction.set_rollback(True)

        self.stdout.write("\nSalidas faltantes (se descuentan): " + ", ".join(f"{k} {v:g}" for k, v in total_more.items()))
        self.stdout.write("Devoluciones (se reintegran): " + ", ".join(f"{k} {v:g}" for k, v in total_less.items()))
        if opts["apply"]:
            if touched_all:
                broadcast_inventory(tenant.id, touched_all, moves_all)
            self.stdout.write(self.style.SUCCESS(f"Aplicado: {len(moves_all)} movimientos."))
        else:
            self.stdout.write(self.style.WARNING("Simulación. Usa --apply para escribir."))

    @staticmethod
    def demand_to_items(tenant, demand):
        """Misma regla que consume_recipe_demand, sin escribir nada."""
        out = defaultdict(float)
        simple = {p.id: p for p in models.Product.objects.filter(id__in=demand.keys(), kind="simple", inventory_item__isnull=False)}
        compound_ids = [pid for pid in demand if pid not in simple]
        recipes = {r.product_id: r for r in models.Recipe.objects.filter(product_id__in=compound_ids).prefetch_related("ingredients")}
        from api.views import ingredient_consumption
        items = {}
        for pid, qty in demand.items():
            p = simple.get(pid)
            if p is not None:
                out[p.inventory_item_id] += float(p.inventory_qty or 1) * float(qty)
                continue
            r = recipes.get(pid)
            if not r:
                continue
            portions = max(r.portions, 1)
            for ing in r.ingredients.all():
                if ing.item_id is None:
                    continue
                if ing.item_id not in items:
                    items[ing.item_id] = models.InventoryItem.objects.get(pk=ing.item_id)
                out[ing.item_id] += ingredient_consumption(ing, items[ing.item_id]) / portions * float(qty)
        return out
