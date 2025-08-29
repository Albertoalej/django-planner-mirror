from django.urls import path
from django.contrib.auth.decorators import login_required
from .views import (
    DashboardView,
    OrderDetailPartialView,
    OrdersCardsPartialView,
    OrderCompleteView,
    KpisPartialView,
)
# NUEVO: vistas de error en un módulo separado para no tocar tu views.py
from .views_error import OrderErrorToggleView, OrderErrorSaveView

urlpatterns = [
    path('', login_required(DashboardView.as_view()), name='dashboard'),
    path('orders/cards/', login_required(OrdersCardsPartialView.as_view()), name='orders-cards'),
    path('orders/<int:pk>/detail/', login_required(OrderDetailPartialView.as_view()), name='order-detail'),
    path('orders/<int:pk>/complete/', login_required(OrderCompleteView.as_view()), name='order-complete'),
    path('kpis/', login_required(KpisPartialView.as_view()), name='kpis'),

    # === NUEVO ===
    path('orders/<int:pk>/error/toggle/', login_required(OrderErrorToggleView.as_view()), name='order-error-toggle'),
    path('orders/<int:pk>/error/save/',   login_required(OrderErrorSaveView.as_view()),   name='order-error-save'),
]
