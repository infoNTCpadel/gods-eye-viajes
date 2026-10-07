GOD'S EYE VIAJES — Fase 2B (en tu VPS)
=======================================

Qué es: viaje privado con código (6 letras). El organizador crea la
ruta; todo el grupo ve lo mismo, sube fotos/sitios y al final ve un
Replay que se para en cada sitio con su foto. Descargable en vídeo.

Novedades 2B:
- Fotos y sitios EN EL SERVIDOR: cualquier miembro sube con el botón
  📸 (foto → título → Guardar, 2-3 toques). Se ven en el muro de
  Lugares (por "Ana", agrupadas por parada) y como pins en el mapa.
  Solo el autor o el organizador puede borrar una foto.
- Textos cortos: la invitación vive en el botón "Compartir viaje"
  de la cabecera (código + enlace + WhatsApp), no siempre visible.
- Replay: se para 3 s en cada sitio mostrando su foto grande, y en
  Replay hay "⬇ Descargar Replay en vídeo" (WebM vertical 720x1280
  grabado con Canvas; si el navegador no puede, descarga un PNG).

Datos en tu servidor (volumen Docker gods-eye-data):
- SQLite: /data/app.db (viajes, miembros, paradas, lugares)
- Fotos: /data/photos/<viaje>/<uuid>.jpg, servidas en
  /api/photos/<viaje>/<fichero> sin token: la URL lleva un uuid no
  adivinable; quien tenga esa URL exacta ve esa foto. No publiques
  esas URLs si no quieres compartir esa foto.
- No hagas "docker compose down -v" o borras los viajes y las fotos.

DESPLIEGUE (repo: infoNTCpadel/gods-eye-viajes)
------------------------------------------------
Ya desplegado:
  cd /opt/gods-eye-viajes
  git pull
  docker compose up -d --build
  curl -s https://viajes.ntcpadel.com/api/health   -> {"ok": true}

Desde cero: DNS A de "viajes" a tu IP, git clone del repo,
cp .env.example .env (solo DOMAIN), docker compose up -d --build.

PRUEBA EN 2 MINUTOS (dos móviles)
---------------------------------
1. A crea el viaje y pasa el código (botón Compartir viaje).
2. B entra con código + apodo.
3. A añade una parada en Ruta. B la ve y pulsa "✓ Hemos llegado".
4. B pulsa 📸, hace una foto, Guardar en el viaje.
5. A la ve en Lugares y en el mapa; Replay se para en esa foto.
6. En Replay: "⬇ Descargar Replay en vídeo" y compártelo.

SI ALGO FALLA
-------------
- /api/health sin {"ok": true}: mira docker compose ps y logs.
- 404/autofirmado de Traefik: contenedor no Up; el compose no debe
  declarar "networks" (tu Traefik va en modo host, como padel-app).
- Pantalla vieja en el móvil: cierra y reabre la PWA (caché v5).
- GPS: hace falta HTTPS y permiso; sin moverte, "Simular paseo".
