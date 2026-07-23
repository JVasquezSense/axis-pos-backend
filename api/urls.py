from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("menu/categories", views.CategoryViewSet, basename="category")
router.register("menu/products", views.ProductViewSet, basename="product")
router.register("inventory", views.InventoryViewSet, basename="inventory")
router.register("tables", views.TableViewSet, basename="table")
router.register("recipes", views.RecipeViewSet, basename="recipe")
router.register("customers", views.CustomerViewSet, basename="customer")
router.register("orders", views.OrderViewSet, basename="order")
router.register("suppliers", views.SupplierViewSet, basename="supplier")
router.register("purchases", views.PurchaseViewSet, basename="purchase")
router.register("reservations", views.ReservationViewSet, basename="reservation")
router.register("sales", views.SaleViewSet, basename="sale")
router.register("returns", views.CreditNoteViewSet, basename="credit-note")
router.register("employees", views.EmployeeViewSet, basename="employee")
router.register("admin/tenants", views.AdminTenantViewSet, basename="admin-tenant")
router.register("whatsapp/customers", views.WhatsAppCustomerViewSet, basename="wa-customer")
router.register("whatsapp/orders", views.WhatsAppOrderViewSet, basename="wa-order")
router.register("whatsapp/config", views.WhatsAppConfigViewSet, basename="wa-config")

urlpatterns = router.urls + [
    path("auth/me/", views.MeView.as_view(), name="auth-me"),
    path("dashboard/summary/", views.DashboardView.as_view(), name="dashboard-summary"),
    path("reports/executive/", views.ReportsView.as_view(), name="reports-executive"),
    path("reports/dish-consumption/", views.DishConsumptionView.as_view(), name="reports-dish-consumption"),
    path("admin/metrics/", views.AdminMetricsView.as_view(), name="admin-metrics"),
    # Endpoints públicos para pedidos web + QR por mesa (backlog #8).
    path("public/<slug>/menu/", views.PublicMenuView.as_view(), name="public-menu"),
    path("public/<slug>/order/", views.PublicOrderView.as_view(), name="public-order"),
    path("public/order/<str:order_id>/", views.PublicOrderStatusView.as_view(), name="public-order-status"),
]
