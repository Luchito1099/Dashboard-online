# Notas de diseño y mejoras · Base de datos KLYNEA

> Documento **manual** (no se sobrescribe). El esquema completo y siempre actualizado está en
> [`ESQUEMA_BD.md`](ESQUEMA_BD.md), generado con `python manage.py esquema_bd`.

## 1. Cómo fluye la información hoy

```
Fuente de pedidos (Integracion: Shopify / WooCommerce / … / "Registro manual")
        │   sync / webhook / alta manual
        ▼
   Pedido  ── items ──►  PedidoItem   (líneas de producto, texto libre)
     │  ├─ PedidoSeguimiento (1:1)  → llamada, etapa embudo, tipo cliente, estrategia, vendedor*
     │  └─ PedidoEditLog (1:N)      → historial de cambios + reversión
     ▼
  Avances (KPIs) ──► MetaVendedor (meta diaria por vendedor)
```

- **`Integracion`** abstrae el origen mediante `proveedor` + `categoria`. Cada `Pedido` cuelga de
  una integración (los manuales, de una integración sembrada "Registro manual", `proveedor='manual'`).
- **`unique_together (integracion, external_id)`** hace que la sincronización sea idempotente
  (upsert) por fuente. Esto es lo que permitirá agregar más fuentes sin colisiones.
- `Pedido.vendedor`, `registrado_por` y `editado_por` son 3 FKs distintos a `auth_user`
  (atribución, autoría, último editor).

## 2. El problema de los nombres de producto (prioritario)

**Situación:** `PedidoItem` guarda el producto como **texto libre** (`nombre`, `sku`, `vendor`,
`product_id`, `variant_id`). El mismo producto físico llega con **nombres distintos** según la
fuente (Shopify tienda A vs. tienda B vs. Novashop vs. alta manual). Además existe un catálogo
`productos_producto` que **NO está vinculado** a las líneas de pedido. Resultado: no se puede medir
"ventas por producto" de forma fiable ni deduplicar.

### Mejora recomendada (en 2 fases)

**Fase 1 — Vincular líneas al catálogo canónico**
- Agregar a `PedidoItem`:
  - `producto = FK(productos.Producto, null=True, blank=True, on_delete=SET_NULL)` → producto canónico.
- En la UI de Pedidos, permitir "vincular" manualmente una línea sin mapear a un `Producto`.
- Así el `nombre` crudo de la fuente se conserva (auditoría) pero las métricas usan `producto`.

**Fase 2 — Mapeo automático por alias**
- Nueva tabla **`ProductoAlias`** para auto-mapear en cada sync:
  ```
  ProductoAlias
    producto      FK → productos_producto      # destino canónico
    integracion   FK → integraciones_integracion (null=True → alias global)
    nombre_externo varchar                      # nombre tal como llega de la fuente
    sku_externo    varchar (blank)
    external_product_id varchar (blank)         # match exacto por id de la fuente
    unique_together (integracion, nombre_externo)
  ```
- En `_guardar_pedido_shopify` (y futuros conectores), al crear cada `PedidoItem`:
  1. Buscar `ProductoAlias` por `external_product_id` (match exacto) o por `nombre_externo`.
  2. Si existe → setear `PedidoItem.producto`. Si no → dejar sin vincular y mostrarlo en una
     bandeja "productos sin reconocer" para que un admin lo asocie una vez (y se cree el alias).
- Beneficio: el mismo producto con 5 nombres distintos termina apuntando a **un solo** `Producto`.

**Reporte que habilita:** una tarjeta "Pedidos/ventas por producto" en Avances, consistente entre
todas las fuentes.

## 3. Cuando se agreguen más fuentes (Novashop, etc.)

El modelo ya está preparado; el patrón para una fuente nueva es:
1. Agregar `PROVEEDOR_NOVASHOP` a `Integracion.PROVEEDOR_CHOICES`.
2. Conector `extraer_pedidos_novashop()` + `_guardar_pedido_novashop()` (mapea su JSON → `Pedido`).
3. Registrarlo en el dispatcher de `connectors.py`.
4. (Webhook opcional, como el de Shopify).

Puntos a cuidar al escalar:
- **`tipo_envio` es texto libre** → con varias fuentes se ensucia (ya se vio el datalist repetido).
  Recomendado: catálogo `TipoEnvio` o normalizar a choices (Agencia / Delivery / Courier / Otros).
- **Índices**: al crecer el volumen, agregar `db_index=True` (o `Meta.indexes`) en
  `Pedido.fecha_pedido`, `Pedido.estado`, `Pedido.vendedor` y `Pedido.origen` (se filtran/ordenan).
- **Multimoneda**: `Pedido.moneda` por pedido — si entran fuentes en otra moneda, los KPIs en S/
  necesitarán conversión.

## 4. Otras observaciones del esquema actual

- **`Pedido.estado` vs `PedidoSeguimiento.etapa_embudo`**: ahora comparten exactamente los mismos
  valores (se unificaron). Quedan como **dos campos** que pueden divergir a propósito (el "estado"
  operativo vs. la "etapa" de gestión). Si en la práctica siempre van iguales, conviene **eliminar
  `etapa_embudo`** y derivar el funnel directo de `estado` para no mantener dos fuentes de verdad.
- **`PedidoEditLog`** guarda los valores como **etiquetas de texto** (legibles para el historial).
  La reversión re-mapea la etiqueta → valor; es algo frágil para FKs (vendedor/estrategia se buscan
  por nombre). Si se vuelve crítico, guardar también el valor crudo (`valor_anterior_raw`).
- **`MetaVendedor`** es meta diaria fija. Si se quieren metas por mes o históricos de cumplimiento,
  haría falta una tabla con fecha (`MetaVendedorDia` o registro de cumplimiento por día).

## 5. Mantener este documento al día

- El esquema (`ESQUEMA_BD.md`) se regenera con:
  ```
  python manage.py esquema_bd
  ```
  Ejecútalo después de cada `makemigrations` que cambie modelos.
- Para verlo como diagrama: pega el bloque **Mermaid** en https://mermaid.live o el bloque
  **DBML** en https://dbdiagram.io.
