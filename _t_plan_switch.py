import os, django, sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")
os.environ["DATABASE_URL"]=os.environ["DATABASE_PUBLIC_URL"]
django.setup()
from api import models
slug = sys.argv[1]; new = sys.argv[2] if len(sys.argv)>2 else None
t = models.Tenant.objects.get(slug=slug)
print("antes:", t.name, t.plan, "override", t.features)
if new:
    t.plan = new; t.save(update_fields=["plan"])
    t.refresh_from_db()
    eff = t.effective_features()
    print("ahora:", t.plan, "maxUsers", t.max_users,
          "| inventory", eff.get("inventory"), "reports", eff.get("reports"), "qr", eff.get("qr"))
