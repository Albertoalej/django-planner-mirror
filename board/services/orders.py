from django.utils import timezone
from datetime import datetime, timedelta
from .erp import fetch_orders, fetch_items
from ..models import OrdenUIState

def build_cards(date_from=None, search=None, view_mode="relevantes", limit=None):
    """
    - Relevantes: trae del ERP por fecha mínima (hoy por defecto) y opcional búsqueda.
    - Pasados: NO barrer el ERP completo; tomar doc_ids finalizados (local) y
      luego pedir SOLO esos doc_ids al ERP.
    - 'first_seen_at' fija la hora visible (ERP trae 00:00).
    """
    tz = timezone.get_current_timezone()
    today = timezone.localdate()

    # ====== RUTA RELEVANTES (rápida por fecha) ======
    if view_mode == "relevantes":
        # Si no te pasan date_from, usamos HOY (minimizas lecturas)
        if not date_from:
            # 00:00 locales de hoy
            date_from = datetime.combine(today, datetime.min.time())
            date_from = timezone.make_aware(date_from, tz)

        raw_orders = fetch_orders(date_from=date_from, search=search, limit=limit)
        target_doc_ids = [r['doc_id'] for r in raw_orders]

    # ====== RUTA PASADOS (rápida por doc_ids) ======
    else:  # "pasados"
        # Tomamos de la DB local SOLO los finalizados de días previos (y opcional límite)
        qs = (OrdenUIState.objects
              .filter(is_finalizado=True, fecha_finalizacion__lt=timezone.now().replace(hour=0, minute=0, second=0, microsecond=0))
              .order_by('-fecha_finalizacion'))

        # Si quieres paginar, ajusta este límite (ej. últimos 500)
        MAX_DOCS = 500
        ui_rows = list(qs.values_list('doc_id', flat=True)[:MAX_DOCS])

        if not ui_rows:
            raw_orders = []
            target_doc_ids = []
        else:
            # Puedes además recortar por rango de fechas del ERP (opcional), pero al ir por doc_ids ya es rápido
            raw_orders = fetch_orders(search=search, limit=None, doc_ids=ui_rows)
            target_doc_ids = ui_rows

    # ====== Carga estados existentes solo de los doc_ids que sí tenemos ======
    existing = { s.doc_id: s for s in OrdenUIState.objects.filter(doc_id__in=target_doc_ids) }

    cards = []
    to_save = []

    for r in raw_orders:
        doc_id = r['doc_id']
        ui = existing.get(doc_id)

        # first_seen_at
        if ui is None:
            ui = OrdenUIState(doc_id=doc_id, first_seen_at=timezone.now())
            existing[doc_id] = ui
            to_save.append(ui)
        elif ui.first_seen_at is None:
            ui.first_seen_at = timezone.now()
            to_save.append(ui)

        is_final = bool(ui and ui.is_finalizado)
        fecha_final = ui.fecha_finalizacion if is_final else None
        status = 'FINALIZADO' if is_final else r['status_erp']

        # Combinar fecha ERP + hora de first_seen_at
        erp_dt = r['fecha_creacion']
        date_part = erp_dt.date() if hasattr(erp_dt, "date") else erp_dt
        seen_local = timezone.localtime(ui.first_seen_at)
        combined = datetime.combine(date_part, seen_local.time())
        if timezone.is_naive(combined):
            combined = timezone.make_aware(combined, tz)

        # Filtro de vista
        if view_mode == "relevantes":
            if status == 'FINALIZADO':
                if not fecha_final or fecha_final.date() != today:
                    continue
        else:  # pasados
            if not (status == 'FINALIZADO' and fecha_final and fecha_final.date() < today):
                continue

        # Normaliza folio a int si se puede
        folio_val = r['folio']
        try:
            folio_val = int(str(folio_val).strip())
        except Exception:
            pass

        # === NUEVO: persistir folio en OrdenUIState si el modelo lo tiene ===
        try:
            if hasattr(ui, "folio") and ui.folio != folio_val:
                ui.folio = folio_val
                if ui not in to_save:
                    to_save.append(ui)
        except Exception:
            # Seguridad: no fallar si aún no existe el campo en la DB
            pass

        cards.append({
            "pk": doc_id,
            "folio": folio_val,
            "cliente": r['cliente'],
            "fecha_creacion": combined,
            "fecha_finalizacion": fecha_final,
            "vendedor": r['vendedor'],
            "status": status,
            "almacen": r.get('almacen_calc') or 'Mixto',
            "fecha_entrega": r['fecha_entrega'],
            "metodo_entrega": r['metodo_entrega'],

            # === NUEVO: estado de error (proveniente de OrdenUIState) ===
            "has_error": bool(ui and getattr(ui, "has_error", False)),
            "error_responsable": (
                ui.error_responsable.nombre if (ui and getattr(ui, "error_responsable", None)) else None
            ),
            "error_resuelto": bool(ui and getattr(ui, "error_resuelto", False)),
            "error_comentarios": (ui.error_comentarios if (ui and getattr(ui, "error_comentarios", "")) else ""),
            "is_finalizado": bool(ui and getattr(ui, "is_finalizado", False)),
        })

    # Guarda first_seen_at si faltaba
    for obj in to_save:
        obj.save()

    # Orden estable por folio asc + desempate por pk
    def _as_int(val, big=10**12):
        try:
            return int(str(val).strip())
        except Exception:
            return big
    cards.sort(key=lambda r: (_as_int(r.get("folio")), int(r.get("pk", 0))))

    return cards


def get_order_items(doc_id):
    return fetch_items(doc_id)
