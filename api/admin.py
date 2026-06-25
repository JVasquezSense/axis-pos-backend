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
    models.Supplier,
    models.Purchase,
    models.PurchaseLine,
    models.Reservation,
    models.Sale,
    models.Employee,
):
    admin.site.register(model)
