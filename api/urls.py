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

urlpatterns = router.urls
