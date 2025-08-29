from django.views import View
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from .models import OrdenUIState, EmpleadoResponsable
from .services.orders import build_cards, get_order_items

# Reutilizamos tu helper para mantener exactamente el mismo comportamiento de filtros
from .views import _extract_filters


@method_decorator(login_required, name='dispatch')
class OrderErrorToggleView(View):
    """
    Alterna has_error. Si se apaga, limpia responsable / resuelto / comentarios.
    Devuelve solo el partial de controles (HTMX), como haces con el toggle de finalizar.
    """
    template_name = "board/_order_error_controls.html"

    def post(self, request, pk):
        ui, _ = OrdenUIState.objects.get_or_create(doc_id=pk)

        # === Guard: solo permitir cuando la orden está FINALIZADA ===
        if not ui.is_finalizado:
            return HttpResponseForbidden("Solo se puede marcar error cuando la orden está FINALIZADA.")

        ui.has_error = not ui.has_error
        if not ui.has_error:
            ui.error_responsable = None
            ui.error_resuelto = False
            ui.error_comentarios = ""
        ui.save()

        # Recalcula tarjetas para mantener coherencia (igual que tu flujo actual)
        q, view_mode, date_from = _extract_filters(request)
        cards = build_cards(date_from=date_from, search=q, view_mode=view_mode, limit=None)
        orden = next((c for c in cards if c["pk"] == pk), None)
        # items queda intacto; no lo necesitamos para este partial

        return render(request, self.template_name, {
            "orden": orden,
            "responsables": EmpleadoResponsable.objects.filter(activo=True).order_by("nombre"),
        })


@method_decorator(login_required, name='dispatch')
class OrderErrorSaveView(View):
    """
    Guarda los detalles del error:
    - responsable (FK a EmpleadoResponsable)
    - error_resuelto (checkbox)
    - comentarios (texto)
    Siempre deja has_error en True (porque es un 'guardar' del bloque activo).
    """
    template_name = "board/_order_error_controls.html"

    def post(self, request, pk):
        ui, _ = OrdenUIState.objects.get_or_create(doc_id=pk)

        # === Guard: solo permitir cuando la orden está FINALIZADA ===
        if not ui.is_finalizado:
            return HttpResponseForbidden("Solo se puede marcar error cuando la orden está FINALIZADA.")

        ui.has_error = True

        # Responsable
        resp_id = (request.POST.get("error_responsable") or "").strip()
        if resp_id.isdigit():
            ui.error_responsable = EmpleadoResponsable.objects.filter(id=int(resp_id), activo=True).first()
        else:
            ui.error_responsable = None

        # ¿Se solucionó?
        ui.error_resuelto = (request.POST.get("error_resuelto") == "on")

        # Comentarios
        ui.error_comentarios = (request.POST.get("error_comentarios") or "").strip()

        ui.save()

        # Recalcula tarjetas para mantener coherencia (igual que tu flujo actual)
        q, view_mode, date_from = _extract_filters(request)
        cards = build_cards(date_from=date_from, search=q, view_mode=view_mode, limit=None)
        orden = next((c for c in cards if c["pk"] == pk), None)

        return render(request, self.template_name, {
            "orden": orden,
            "responsables": EmpleadoResponsable.objects.filter(activo=True).order_by("nombre"),
        })
