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
router.register("employees", views.EmployeeViewSet, basename="employee")
router.register("admin/tenants", views.AdminTenantViewSet, basename="admin-tenant")

urlpatterns = router.urls + [
    path("dashboard/summary/", views.DashboardView.as_view(), name="dashboard-summary"),
    path("reports/executive/", views.ReportsView.as_view(), name="reports-executive"),
    path("admin/metrics/", views.AdminMetricsView.as_view(), name="admin-metrics"),
]
