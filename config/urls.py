"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns = [
    # Redirect root to API documentation
    path(
        "",
        RedirectView.as_view(url="/swagger/", permanent=False),
        name="index",
    ),
    # Admin
    path("admin/", admin.site.urls),
    # API routes
    path("api/v1/auth/", include("apps.accounts.api.urls")),
    path("api/v1/", include("apps.products.api.urls")),
    path("api/v1/", include("apps.cart.api.urls")),
    path("api/v1/", include("apps.orders.api.urls")),
    path("api/v1/", include("apps.payments.api.urls")),
    path("api/v1/", include("apps.notifications.api.urls")),
    path("api/v1/", include("apps.inventory.api.urls")),
    # API Documentation with drf-spectacular
    path("swagger.json", SpectacularAPIView.as_view(), name="schema"),
    path(
        "swagger/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"
    ),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL, document_root=settings.MEDIA_ROOT
    )

# Format, sort imports, and check all in one line
# black apps/ --exclude "migrations|__pycache__|venv|env|tests" --line-length 79 && isort apps/ --skip migrations --skip __pycache__ --skip tests --profile black --line-length 79 && flake8 apps/ --exclude migrations,__pycache__,venv,env,tests --max-line-length 79 --extend-ignore E203,W503