# Cómo conectar Meta Ads (Graph API) → KLYNEA ERP — conexión DIRECTA

## La arquitectura

```
┌─────────────┐    Graph API (token)    ┌──────────────────────────┐
│  Meta Ads   │ ◄──────────────────────►│        KLYNEA ERP        │
│ (Graph API) │   el ERP extrae solo    │  anuncios/connectors.py  │
└─────────────┘                         │  Probar · Sincronizar    │
                                        └──────────────────────────┘
```

El **ERP se conecta directo** a la Graph API de Meta: guardas el **token** en la cuenta
publicitaria (cifrado en BD) y el ERP extrae los insights por sí mismo — igual que el connector
de Shopify en Integraciones. **No necesitas n8n para la extracción.**

> (El webhook `/publicidad/webhook/n8n/` sigue disponible como alternativa, pero la vía principal
> y recomendada es la conexión directa de abajo.)

---

## Paso 1 — Token en Meta (una sola vez)

1. **Business Manager** → *Configuración del negocio* → **Usuarios del sistema** → crea un
   **System User**.
2. **Agregar activos** → asígnale tu **cuenta publicitaria** con acceso de lectura.
3. **Generar token** para ese system user, con el permiso **`ads_read`** (también `read_insights`).
   Requiere una **App** con *Marketing API*. El token de system user **no expira**.
4. Anota:
   - `ACCESS_TOKEN`
   - `AD_ACCOUNT_ID` → con prefijo `act_`, ej. `act_123456789`

---

## Paso 2 — Configurar la cuenta en el ERP

**Publicidad › Ajustes › Cuentas publicitarias → Agregar / actualizar cuenta:**
- **ad_account_id:** `act_123456789`
- **Nombre:** ej. `KLYNEA PE`
- **Tienda asociada:** la fuente de pedidos (KLYNEA / NovaShop) para atribuir y filtrar.
- **Versión API:** `v21.0` (por defecto).
- **Access token:** pégalo aquí (se guarda **cifrado**). Al editar, déjalo vacío para conservarlo.

Luego, en la fila de la cuenta:
- **Probar** → valida token + cuenta (`GET /act_<id>?fields=name,currency`).
- **↻ Sincronizar** → extrae los insights de los últimos 30 días.

---

## Paso 3 — Qué extrae el ERP (Graph API)

`anuncios/connectors.py → sincronizar()` hace dos llamadas a
`/{api_version}/{ad_account_id}/insights` (con paginación):

1. **Diario** (`level=ad`, `time_increment=1`): `campaign_id, campaign_name, adset_id, adset_name,
   ad_id, ad_name, spend, impressions, clicks, actions, account_currency`.
   - De `actions` saca **resultados** sumando los `action_type` relevantes (compra, lead, o
     `messaging_conversation_started_7d` para campañas de mensajes). Ajustable en
     `connectors.ACCIONES_RESULTADO`.
2. **Horario** (`breakdowns=hourly_stats_aggregated_by_advertiser_time_zone`): para el heatmap;
   la **hora** sale de la franja `"14:00:00 - 14:59:59"` → `14`.

Ambas se guardan reutilizando `services.ingerir_payload`, que **respeta `incluir_en_extraccion`**:
solo se almacenan insights de los anuncios que marcaste en Ajustes (la estructura del anuncio
siempre se guarda para que puedas marcarlo).

---

## Paso 4 — Flujo de uso

1. **Ajustes:** crea la cuenta con su token → **Probar** → **Sincronizar**.
2. **Ajustes › ¿Qué anuncios entran al pipeline?:** marca los anuncios que quieres y guarda.
3. **Sincroniza de nuevo** → ahora sí guarda los insights de los marcados.
4. **Matching:** asigna producto a cada anuncio nuevo (con sugerencias automáticas).
5. **Diario / Por producto / Heatmap** quedan poblados.

---

## Paso 5 — Automatizar (cron)

Para que se actualice solo, programa el comando (en cron del servidor o disparado por n8n):

```bash
python manage.py sincronizar_ads            # últimos 30 días, todas las cuentas activas con token
python manage.py sincronizar_ads --dias 7   # ventana corta para correr seguido
```

Y para las alertas de CPA alto (→ Telegram vía n8n):

```bash
python manage.py alertas_ads
```

---

## Atribución directa por anuncio (UTM)

Para saber de **qué anuncio** vino cada pedido (no solo por producto), arma los links de tus
anuncios con tracking; el ERP ya lee UTM del pedido en `integraciones/connectors.py`:

```
https://tutienda.com/products/faja?utm_source=fb&utm_campaign={{campaign.name}}&utm_content={{ad.id}}&ad_id={{ad.id}}
```

Con `ad_id={{ad.id}}` se casa el pedido directo al anuncio; si no, se usa el match por producto
(obligatorio en campañas de **mensajes**, donde no hay link).

---

## Resolución de problemas

- **Probar falla con "Meta: … (código 190)"** → token inválido/expirado o sin `ads_read`.
- **Probar falla con código 100 / "Unsupported get request"** → `ad_account_id` mal escrito
  (debe llevar `act_`).
- **Sincroniza pero no aparecen insights** → el anuncio no está marcado en "¿Qué anuncios entran
  al pipeline?" (su estructura sí se guarda; márcalo y vuelve a sincronizar).
- **No aparecen pedidos en la tabla por producto** → falta el **matching** producto↔anuncio, o las
  líneas de pedido aún no están vinculadas al catálogo (ProductoAlias).
