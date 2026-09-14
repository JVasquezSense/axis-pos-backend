import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from api import models
from collections import Counter
for t in models.Tenant.objects.all():
    rs = models.Recipe.objects.filter(tenant=t).select_related("product")
    if not rs.exists(): continue
    print(f"== {t.slug} ==")
    cnt = Counter(r.product_id for r in rs if r.product_id)
    for r in rs:
        pname = r.product.name if r.product else "(sin producto)"
        flag = ""
        if r.product and r.name.strip().lower() != r.product.name.strip().lower(): flag += " <-- NOMBRE DISTINTO"
        if r.product_id and cnt[r.product_id] > 1: flag += " <-- PRODUCTO CON VARIAS RECETAS"
        if flag: print(f"  receta#{r.id} '{r.name}' -> producto#{r.product_id} '{pname}' porciones={r.portions}{flag}")
    b = [r for r in rs if "bombastic" in r.name.lower()]
    for r in b:
        print(f"  BOMBASTIC receta#{r.id} porciones={r.portions}:", [(i.name, float(i.quantity), i.unit) for i in r.ingredients.all()])
