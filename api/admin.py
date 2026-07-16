from django.contrib import admin
from . import models

for model in (
    models.Tenant,
    models.UserProfile,
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
    models.WhatsAppCustomer,
    models.WhatsAppOrder,
    models.WhatsAppOrderLine,
    models.WhatsAppConfig,
):
    admin.site.register(model)
