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

BOTE COMÚN
----------
- Si hacéis fondo común: elegid quién lo lleva (tesorero). Botón
  "Aportar al bote" (importe → Aportar). La aportación nace PENDIENTE
  y solo cuenta cuando el tesorero la confirma (Confirmar/Rechazar).
- La tesorera puede apuntar la aportación de un compañero sin móvil:
  nace ya confirmada. Nadie salvo ella puede apuntar aportaciones
  ajenas.
- Al añadir un gasto, el interruptor "Pagado del bote" pone al
  tesorero como pagador.
- Si el bote queda en negativo (el tesorero adelantó dinero), la
  cabecera cambia a "Ana adelantó X €" y SOLO el tesorero ve el botón
  "Pedir para reponer": importe pre-rellenado con lo que el grupo le
  debe según las cuentas, elige a quién se lo pide y botón Pedir
  (3 toques). Tras crearlo, "Compartir por WhatsApp" genera el texto:
  "Ana ha adelantado 20 € del bote 🫙: Bruno 10 €, Carla 10 €".
  La petición NO crea ningún gasto (evitaría doble conteo): solo
  organiza devoluciones de deudas que ya existen; no altera balances
  ni "Saldar cuentas".
- Cada miembro ve su parte en la tarjeta "Ana pide reponer 20 €" con
  "Marcar pagado" (1 toque); cuando todos pagan, la tarjeta se marca
  "✓ Reembolsado". El pago se registra como settlement vinculado a
  la petición; no se puede pagar de más.
- Nota: tras reembolsar, el bote puede mostrar un pequeño residual negativo
  igual a lo que el tesorero consumió del bote por encima de su propia
  aportación (ej.: su parte de la cena 110 € menos sus 100 € aportados
  = 10 € que salieron de su bolsillo para su propio consumo). Es
  correcto contablemente; "Pedir para reponer" se pre-rellena con 0
  porque el grupo ya no le debe nada.

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
