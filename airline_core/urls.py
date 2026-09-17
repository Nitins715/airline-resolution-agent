from django.contrib import admin
from django.urls import path, include
from resolution_agent.views import IndexView

urlpatterns = [
    path('', IndexView.as_view(), name='home'),
    path('admin/', admin.site.urls),
    path('api/', include('resolution_agent.urls')),
]
