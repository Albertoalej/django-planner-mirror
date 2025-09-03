from django.contrib import admin
from .models import OrdenUIState, EmpleadoResponsable

@admin.register(OrdenUIState)
class OrdenUIStateAdmin(admin.ModelAdmin):
    list_display = ("doc_id", "folio", "is_finalizado", "has_error", "error_responsable", "error_resuelto", "updated_at")
    list_filter = ("is_finalizado", "has_error", "error_resuelto")
    search_fields = ("doc_id", "folio",)

@admin.register(EmpleadoResponsable)
class EmpleadoResponsableAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre",)
