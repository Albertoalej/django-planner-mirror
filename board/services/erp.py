from django.db import connections
from django.db.utils import OperationalError

def fetch_orders(date_from=None, date_to=None, search=None, limit=None, doc_ids=None):
    """
    Lee pedidos del ERP (MSSQL) con filtros:
      - date_from / date_to: rango de D.CFECHA (incluyente / excluyente según convenga)
      - search: folio (numérico) o cliente (LIKE)
      - limit: TOP n
      - doc_ids: lista de CIDDOCUMENTO a incluir (acelera 'pasados')
    Devuelve:
      doc_id, folio, cliente, fecha_creacion, fecha_entrega, observ,
      total_u, pend_u, vendedor, almacen_calc, metodo_entrega, status_erp
    """
    where = ["D.CIDCONCEPTODOCUMENTO = 2"]
    params = []

    if date_from:
        where.append("D.CFECHA >= %s")
        params.append(date_from)
    if date_to:
        where.append("D.CFECHA < %s")
        params.append(date_to)

    # filtro por doc_ids (MUY útil para 'pasados')
    if doc_ids:
        # arma una lista de placeholders
        placeholders = ",".join(["%s"] * len(doc_ids))
        where.append(f"D.CIDDOCUMENTO IN ({placeholders})")
        params.extend(doc_ids)

    if search:
        s_raw = str(search).strip()
        s_digits = ''.join(ch for ch in s_raw if ch.isdigit())
        if s_digits:
            where.append("(D.CFOLIO = %s OR CAST(D.CFOLIO AS VARCHAR(50)) LIKE %s)")
            params.extend([int(s_digits), f"%{s_digits}%"])
        else:
            where.append("D.CRAZONSOCIAL LIKE %s")
            params.append(f"%{s_raw}%")

    where_clause = " AND ".join(where)
    top_clause = f"TOP ({int(limit)})" if limit else ""
    order_in_cte = "ORDER BY D.CFECHA DESC" if limit else ""

    # NOTA: limit -> ORDER BY en CTE; sin limit -> ORDER BY solo al final
    sql = f"""
    ;WITH base AS (
      SELECT {top_clause}
        D.CIDDOCUMENTO      AS doc_id,
        D.CFOLIO            AS folio,
        D.CRAZONSOCIAL      AS cliente,
        D.CFECHA            AS fecha_creacion,
        D.CFECHAENTREGARECEPCION AS fecha_entrega,
        D.COBSERVACIONES    AS observ,
        D.CREFERENCIA       AS referencia,
        D.CTOTALUNIDADES    AS total_u,
        D.CUNIDADESPENDIENTES AS pend_u,
        A.CNOMBREAGENTE     AS vendedor
      FROM dbo.admDocumentos D
      LEFT JOIN dbo.admAgentes A ON A.CIDAGENTE = D.CIDAGENTE
      WHERE {where_clause}
      {order_in_cte}
    ),
    almacenes AS (
      SELECT
        M.CIDDOCUMENTO AS doc_id,
        MIN(AL.CCODIGOALMACEN) AS min_al,
        MAX(AL.CCODIGOALMACEN) AS max_al
      FROM dbo.admMovimientos M
      JOIN dbo.admAlmacenes AL ON AL.CIDALMACEN = M.CIDALMACEN
      -- ¡ACELERA!: solo movimientos de los doc_id que ya están en 'base'
      JOIN base B ON B.doc_id = M.CIDDOCUMENTO
      GROUP BY M.CIDDOCUMENTO
    )
    SELECT
      B.doc_id, B.folio, B.cliente, B.fecha_creacion, B.fecha_entrega, B.observ, B.referencia,
      B.total_u, B.pend_u, B.vendedor,
      CASE WHEN A.min_al = A.max_al THEN CAST(A.min_al AS varchar(10)) ELSE 'Mixto' END AS almacen_calc
    FROM base B
    LEFT JOIN almacenes A ON A.doc_id = B.doc_id
    ORDER BY
      TRY_CONVERT(int, B.folio) ASC,
      B.folio ASC,
      B.doc_id ASC;
    """

    try:
        with connections['erp'].cursor() as cur:
            cur.execute(sql, params)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except OperationalError:
        return []

    # Post-proceso
    for r in rows:
        obs = (r.get('observ') or '').strip()
        r['metodo_entrega'] = (
            'Paquetería' if '1' in obs else
            'Repartidor' if '2' in obs else
            'Sucursal'   if '3' in obs else
            'Desconocido'
        )
        r['status_erp'] = 'SURTIDO' if r['pend_u'] < r['total_u'] else 'PENDIENTE'
    return rows


def fetch_items(doc_id):
    sql = """
    SELECT
      P.CCODIGOPRODUCTO  AS codigo,
      P.CNOMBREPRODUCTO  AS descripcion,
      AL.CCODIGOALMACEN  AS almacen,
      M.CUNIDADES        AS unidades
    FROM dbo.admMovimientos M
    JOIN dbo.admProductos  P  ON P.CIDPRODUCTO  = M.CIDPRODUCTO
    JOIN dbo.admAlmacenes  AL ON AL.CIDALMACEN  = M.CIDALMACEN
    WHERE M.CIDDOCUMENTO = %s
    ORDER BY P.CCODIGOPRODUCTO;
    """
    try:
        with connections['erp'].cursor() as cur:
            cur.execute(sql, [doc_id])
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    except OperationalError:
        return []
