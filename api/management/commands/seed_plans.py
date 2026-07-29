"""
Seed de los 3 planes SaaS con sus features por defecto.

Uso:
    python manage.py seed_plans

Idempotente: actualiza los planes existentes sin duplicar. Las claves de
features coinciden con las secciones del menú lateral del frontend, más las
capacidades (qr, whatsapp, ai) y el tope de usuarios.
"""
from django.core.management.base import BaseCommand
from api import models


def _starter():
    """Básico: operar el restaurante y su carta. Nada más."""
    f = dict(models._default_features())
    f.update({"menu": True, "history": True, "max_users": 2})
    return f


def _growth():
    """Pro: suma control de costos, clientes, reportes y pedidos web con QR."""
    f = _starter()
    f.update({
        "inventory": True, "suppliers": True, "crm": True, "reports": True,
        "returns": True, "shift-history": True, "weborders": True,
        "audit": True, "qr": True,
        "max_users": 8,
    })
    return f


def _enterprise():
    """Enterprise: todo activo."""
    f = _growth()
    f.update({k: True for k in models.NAV_FEATURES})
    f.update({k: True for k in models.CAPABILITY_FEATURES})
    f["max_users"] = 50
    return f


PLANS = [
    {"code": "starter", "name": "Básico", "max_users": 2, "price": 299000, "features": _starter},
    {"code": "growth", "name": "Pro", "max_users": 8, "price": 599000, "features": _growth},
    {"code": "enterprise", "name": "Enterprise", "max_users": 50, "price": 1200000, "features": _enterprise},
]


class Command(BaseCommand):
    help = "Crea/actualiza los 3 planes SaaS con sus features por defecto."

    def handle(self, *args, **options):
        created, updated = 0, 0
        for p in PLANS:
            feats = p["features"]()
            obj, was_created = models.Plan.objects.update_or_create(
                code=p["code"],
                defaults={
                    "name": p["name"],
                    "max_users": p["max_users"],
                    "price": p["price"],
                    "features": feats,
                },
            )
            on = sorted(k for k, v in feats.items() if v is True)
            self.stdout.write(f"  {obj.name}: {len(on)} modulos, {obj.max_users} usuarios")
            created += 1 if was_created else 0
            updated += 0 if was_created else 1
        self.stdout.write(self.style.SUCCESS(
            f"Planes: {created} creados, {updated} actualizados."
        ))
