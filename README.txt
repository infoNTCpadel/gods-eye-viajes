DIARIO DE VIAJE (pivote God's Eye — uso personal)
=================================================

Qué es: un viaje privado con código de 6 letras donde el grupo de
compañeros comparte tres cosas, y nada más:
1) DIARIO: las fotos del grupo ordenadas por días, como un álbum.
2) GASTOS: quién pagó qué, balances y saldar cuentas al mínimo de pagos.
3) DÓNDE ESTAMOS: mapa con los compañeros que estén compartiendo su
   ubicación, con interruptor de privacidad.

Sin cuentas: se entra con código + apodo. Sin ruta del organizador,
sin replay, sin grabación de recorridos.

DESPLIEGUE (repo: infoNTCpadel/gods-eye-viajes)
------------------------------------------------
  cd /opt/gods-eye-viajes
  git pull
  docker compose up -d --build
  curl -s https://viajes.ntcpadel.com/api/health   -> {"ok": true}

Desde cero: DNS A de "viajes" a tu IP, git clone del repo,
cp .env.example .env (solo DOMAIN), docker compose up -d --build.
No hagas "docker compose down -v" o borras viajes, fotos y gastos.

GASTOS — cómo funciona
----------------------
- Añadir: importe (teclado numérico grande) → descripción → quién pagó
  → reparto Igual por defecto con vista previa en vivo de lo que toca
  a cada uno. Se puede desmarcar a quien no estaba; modos Igual /
  Cantidades / Participaciones (el último modo usado se recuerda).
  Foto del ticket opcional.
- Balances por persona: verde = le deben, rojo = debe.
- "Saldar cuentas": propone quién paga a quién con el mínimo de pagos;
  "Registrar pago" anota un Bizum/efectivo ya hecho (el dinero se mueve
  fuera de la app, la app es el libro).
- Cualquiera puede añadir gastos; solo quien lo registró o el
  organizador puede borrarlo.

BOTE COMÚN (su propia cuenta: 🫙 Bote)
-------------------------------------
- El bote es una cuenta más del viaje (apodo reservado "🫙 Bote"):
  las aportaciones van AL BOTE (no al saldo del tesorero) y los
  gastos "del bote" los paga 🫙 Bote. El tesorero ya no "debe" nada.
- Si hacéis fondo común: elegid quién lo lleva (tesorero). Botón
  "Aportar al bote" (importe → Aportar). La aportación nace PENDIENTE
  y solo cuenta cuando el tesorero la confirma (Confirmar/Rechazar).
- La tesorera puede apuntar la aportación de un compañero sin móvil:
  nace ya confirmada. Nadie salvo ella puede apuntar aportaciones
  ajenas.
- Tarjeta del bote: "🫙 Bote · en caja: X €" + ronda rápida de lo
  aportado por cada uno ("Aportado por: Bruno 100 € · Ana 20 €").
- Al añadir un gasto, el interruptor "Pagado del bote" pone a 🫙 Bote
  como pagador y muestra "Bote: quedan X €".
- El bote NUNCA queda en negativo: si el gasto supera lo que queda,
  el servidor lo rechaza (400). En el formulario aparece "⚠️ Faltan
  Y €" con "Añadir al bote ahora": importe pre-rellenado con Y
  (editable, mínimo Y) + quién aporta (por defecto tú). Al guardar,
  primero se registra la aportación y después el gasto; si la
  aportación falla, el gasto no se guarda. Si quien aporta no lleva
  el bote, la aportación nace pendiente y el gasto se guarda cuando
  el tesorero la confirme.
- Si al final sobra dinero: botón "Repartir sobrante" (solo el
  tesorero), elige entre quiénes (+ "Seleccionar todos") y el bote
  reparte a partes iguales. Del bote solo sale con "Repartir
  sobrante": en "Saldar cuentas" los movimientos del bote salen en
  su propio grupo "🫙 Del bote".

PRIVACIDAD DEL LOCALIZADOR
--------------------------
- OFF por defecto. Al activar eliges duración: 15 min / 1 h / 8 h.
- Caduca solo: el servidor deja de guardar y de exponer tu posición
  cuando se acaba el tiempo; sin sharing activo NO hay posición en la
  base de datos ni en la API.
- Banner visible mientras compartes ("Compartiendo tu ubicación ·
  quedan ~X min"), con botón de apagar en un toque.
- Quien no comparte aparece como "no comparte ubicación": pausar es
  visible para el grupo, no hay modo oculto.
- La posición solo funciona con la app abierta: la PWA no tiene GPS
  en segundo plano (los navegadores no lo permiten). Si cierras la
  app, dejas de actualizar tu posición.
- Las fotos se sirven en /api/photos/<viaje>/<fichero> sin token: la
  URL lleva un uuid no adivinable; quien tenga esa URL exacta ve esa
  foto. No publiques esas URLs si no quieres compartir esa foto.

PRUEBA EN 3 MINUTOS (dos móviles)
---------------------------------
1. A crea el viaje y pasa el código (Compartir viaje).
2. B entra con código + apodo.
3. B pulsa 📸, hace una foto y la guarda. A la ve en el Diario.
4. A añade un gasto "Cena 60 €", paga Ana, participan Ana y B.
   Ambos ven: Ana +30, B −30, y "Saldar: B → Ana 30 €".
5. B registra el pago B→Ana 30 €. Los balances quedan a 0.
6. A activa "Compartir mi ubicación" 15 min. B le ve en el mapa.
   A lo apaga: B ve "no comparte ubicación".

PULIDO MOVIL (caché v12)
-----------------------
- viewport-fit=cover + safe-areas en cabecera, navegación inferior, FAB y toast.
- Inputs/selects a 16px (iOS no hace zoom), botones/chips/acordeones >=48px,
  feedback táctil :active y touch-action:manipulation (sin doble-tap zoom).
- Contenido centrado a 560px, rejilla del Diario 3 columnas, importes grandes,
  truncado elegante de títulos largos, sin scroll horizontal.
- Barra fina de carga al cambiar de pestaña o guardar; estado vacío amable
  en el Diario; navegación inferior con blur y activo claro.
