from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import TemplateView, View
from django.shortcuts import render
from django.http import HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from .models import OrdenUIState, EmpleadoResponsable
from .services.orders import build_cards, get_order_items


def _default_date_from():
    # 25/08/2025 00:00 local
    # Si prefieres naive y que SQL Server lo interprete, puedes pasar string '2025-08-25'
    return "2025-08-27"


def _extract_filters(request):
    q = request.GET.get("q", "").strip() or None
    view_mode = request.GET.get("view", "relevantes")
    date_from = request.GET.get("date_from") or _default_date_from()
    return q, view_mode, date_from


# --- Dashboard (página principal) ---
@method_decorator([login_required, ensure_csrf_cookie], name='dispatch')
class DashboardView(TemplateView):
    template_name = "board/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q, view_mode, date_from = _extract_filters(self.request)

        cards = build_cards(date_from=date_from, search=q, view_mode=view_mode, limit=None)
        kpis = [
            {"label": "Pendientes",  "value": sum(1 for c in cards if c["status"] == "PENDIENTE")},
            {"label": "Surtidos",    "value": sum(1 for c in cards if c["status"] == "SURTIDO")},
            {"label": "Finalizados", "value": sum(1 for c in cards if c["status"] == "FINALIZADO")},
        ]
        ctx.update({
            "sucursal": "TABLERO DE ÓRDENES",
            "kpis": kpis,
            "orders": cards,
            "last_update": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
            "q": q or "",
            "view_mode": view_mode,
            "date_from": date_from,
        })
        return ctx


# --- Detalle (modal) ---
class OrderDetailPartialView(View):
    template_name = "board/_order_detail.html"

    def get(self, request, pk):
        # Mantengo tu mismo flujo/filters para construir 'orden'
        q, view_mode, date_from = _extract_filters(request)
        cards = build_cards(date_from=date_from, search=q, view_mode=view_mode, limit=None)
        orden = next((c for c in cards if c["pk"] == pk), None)

        # Items (como ya lo haces)
        items = get_order_items(pk)

        # ✅ CLAVE: pasar responsables también en este render inicial
        responsables = EmpleadoResponsable.objects.filter(activo=True).order_by("nombre")

        return render(
            request,
            self.template_name,
            {
                "orden": orden,
                "items": items,
                "responsables": responsables,  # <-- esto evita el dropdown vacío "a veces"
            },
        )


# --- Tarjetas (parcial con polling) ---
@method_decorator(ensure_csrf_cookie, name='dispatch')
class OrdersCardsPartialView(View):
    template_name = "board/_cards.html"

    def get(self, request):
        q, view_mode, date_from = _extract_filters(request)
        cards = build_cards(date_from=date_from, search=q, view_mode=view_mode, limit=None)

        since = request.GET.get("since")
        if since:
            dt = parse_datetime(since)
            if dt:
                pass
        return render(request, self.template_name, {
            "orders": cards,
            "now_iso": timezone.now().isoformat(),
        })


# --- KPIs (parcial) ---
@method_decorator(ensure_csrf_cookie, name='dispatch')
class KpisPartialView(View):
    template_name = "board/_kpis.html"

    def get(self, request):
        q, view_mode, date_from = _extract_filters(request)
        cards = build_cards(date_from=date_from, search=q, view_mode=view_mode, limit=None)
        kpis = [
            {"label": "Pendientes",  "value": sum(1 for c in cards if c["status"] == "PENDIENTE")},
            {"label": "Surtidos",    "value": sum(1 for c in cards if c["status"] == "SURTIDO")},
            {"label": "Finalizados", "value": sum(1 for c in cards if c["status"] == "FINALIZADO")},
        ]
        return render(request, self.template_name, {
            "kpis": kpis,
            "last_update": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
        })


# --- Toggle de finalizado (UI-only, sin tocar ERP) ---
@method_decorator(require_POST, name='dispatch')
class OrderCompleteView(View):
    """
    Toggle:
      - Si estaba FINALIZADO (UI) -> reabrir a SURTIDO (UI)
      - Si estaba PENDIENTE/SURTIDO (UI/ERP) -> FINALIZADO (UI)
    Devuelve el parcial según 'context':
      - context=card   -> _card.html (una sola tarjeta)
      - context=detail -> _order_detail.html (contenido del modal)
    """
    def post(self, request, pk):
        context = request.POST.get("context")

        ui, _ = OrdenUIState.objects.get_or_create(doc_id=pk)
        if ui.is_finalizado:
            ui.is_finalizado = False
            ui.fecha_finalizacion = None
        else:
            ui.is_finalizado = True
            ui.fecha_finalizacion = timezone.now()
        ui.save()

        # Recalcular con los filtros actuales para mantener coherencia
        q, view_mode, date_from = _extract_filters(request)
        cards = build_cards(date_from=date_from, search=q, view_mode=view_mode, limit=None)
        orden = next((c for c in cards if c["pk"] == pk), None)
        items = get_order_items(pk)

        if context == "card":
            response = render(request, "board/_card.html", {"o": orden})
            response["HX-Trigger"] = "refreshKpis"
            return response
        elif context == "detail":
            response = render(request, "board/_order_detail.html", {"orden": orden, "items": items})
            response["HX-Trigger"] = "refreshKpis"
            return response

        return HttpResponseBadRequest("Missing or invalid 'context'")
