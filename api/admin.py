from django.contrib import admin
from . import models

for model in (
    models.Tenant,
    models.Category,
    models.Product,
    models.InventoryItem,
    models.InventoryMovement,
    models.Recipe,
    models.Table,
    models.Order,
    models.Customer,
):
    admin.site.register(model)
