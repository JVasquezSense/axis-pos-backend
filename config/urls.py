from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class AxisTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["is_superuser"] = user.is_superuser
        try:
            token["role"] = user.profile.role
        except Exception:
            token["role"] = "admin" if user.is_superuser else "cashier"
        try:
            token["tenant_id"] = str(user.profile.tenant_id)
        except Exception:
            token["tenant_id"] = None
        return token


class AxisTokenView(TokenObtainPairView):
    serializer_class = AxisTokenSerializer


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("api.urls")),
    path("api/v1/auth/token/", AxisTokenView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]
