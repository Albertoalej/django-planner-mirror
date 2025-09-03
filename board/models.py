from django.db import models

class EmpleadoResponsable(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class OrdenUIState(models.Model):
    doc_id = models.BigIntegerField(unique=True, db_index=True)
    folio = models.CharField(max_length=50, db_index=True, blank=True, null=True)
    is_finalizado = models.BooleanField(default=False)
    fecha_finalizacion = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # === NUEVO: datos de error ===
    has_error = models.BooleanField(default=False)
    error_responsable = models.ForeignKey(
        EmpleadoResponsable, null=True, blank=True, on_delete=models.SET_NULL
    )
    error_resuelto = models.BooleanField(default=False)
    error_comentarios = models.TextField(blank=True)

    def __str__(self):
        estado = "FINALIZADO" if self.is_finalizado else "ERP"
        return f"Orden {self.doc_id} ({estado})"


""" correr este codigo para eliminar todo y poner una base nueva
python manage.py shell -c "from board.models import OrdenUIState; OrdenUIState.objects.all().delete()"""