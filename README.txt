GOD'S EYE VIAJES — Fase 2A (viaje privado compartido, en tu VPS)
================================================================

Que es ahora: app de viaje generica God's Eye (oscuro tierra/oro).
El organizador crea un VIAJE PRIVADO y comparte un CODIGO de 6 letras.
El resto entra con ese codigo y su apodo: sin cuentas ni email.
La ruta (paradas, horas, hecho/retraso/reordenar) vive EN EL SERVIDOR
(volumen Docker gods-eye-data, SQLite en /data/app.db), asi que todo el
grupo ve lo mismo: "Ahora toca", proximo punto, cuanto queda segun
horario y progreso de paradas. Los miembros pueden marcar "Hemos
llegado" en la proxima parada; editar/reordenar/retrasar/borrar es
solo del organizador (rol del creador).
El GPS, tus lugares/fotos y el Replay siguen en tu movil por ahora
(la comparticion facil de fotos de todos sera la Fase 2B).
Dominio por defecto: viajes.ntcpadel.com

DESPLIEGUE EN EL VPS (repo GitHub: infoNTCpadel/gods-eye-viajes)
-----------------------------------------------------------------
Ya desplegado antes? Solo actualiza:
  cd /opt/gods-eye-viajes
  git pull
  docker compose up -d --build
  curl -s https://viajes.ntcpadel.com/api/health     -> {"ok": true}

Despliegue desde cero:
  1. DNS: registro A de "viajes" en ntcpadel.com a la IP del VPS.
     Comprueba: getent hosts viajes.ntcpadel.com
  2. cd /opt && git clone https://github.com/infoNTCpadel/gods-eye-viajes.git
     cd gods-eye-viajes
  3. cp .env.example .env  (solo contiene DOMAIN=viajes.ntcpadel.com;
     cambia el dominio ahi si usas otro)
  4. docker compose up -d --build
     - Un solo contenedor python:3-alpine con server.py (solo libreria
       estandar; sirve la PWA y la API /api/ en el puerto 80 interno)
     - Volumen nuevo: gods-eye-data en /data. AHI viven los viajes.
       No hagas "docker compose down -v" o borras los viajes del grupo.
  5. Comprueba: docker compose ps ; curl -s https://viajes.ntcpadel.com/api/health
  6. Abre https://viajes.ntcpadel.com en el movil e instala la PWA
     (menu -> "Anadir a pantalla de inicio").

COMO PROBARLO EN 2 MINUTOS (dos moviles o movil + navegador)
--------------------------------------------------------------
  1. Movil A: "Crear viaje privado" (nombre + tu apodo). Saldra un
     CODIGO grande de 6 letras. Compartelo por WhatsApp (boton de
     invitacion: el enlace lleva ?join=CODIGO y pre-rellena el codigo).
  2. Movil B: abre el enlace, pon su apodo en "Unirme a un viaje" y
     entra. Vera el mismo viaje y a los miembros en la cabecera.
  3. Organizador (A): en Ruta, anade 2 paradas (bodega 11:00, pueblo
     13:30) con su "que hacer". B las ve en segundos (sondeo cada 15 s).
  4. Miembro (B): en la proxima parada pulsa "✓ Hemos llegado".
     A ve el progreso 1/2 y el "Ahora toca" pasa a la segunda parada.
  5. Organizador: prueba ↑/↓, "+20 min retraso" (mueve esa y las
     siguientes) y "📍 Fijar en centro mapa".
  6. Mapa: Grabar con GPS o "Simular paseo" para ver el trazo dorado;
     Lugares y Replay God's Eye como antes.

SI ALGO FALLA
--------------
- /api/health no da {"ok": true}: el contenedor esta con la version
  vieja (estatica) o cayendose. Mira: docker compose ps y
  docker compose logs --tail=50 gods-eye-viajes ; luego git pull +
  docker compose up -d --build.
- 404 de Traefik o certificado autofirmado: el contenedor no esta Up
  o Traefik no lo ve. Tu Traefik va en modo host y el compose, como
  el de padel-app, no declara red externa: no anadas "networks".
- "Sin conexion con el servidor del viaje" dentro de la app: estas en
  una copia vieja en cache. Cierra y reabre la PWA (cache v4) o abre
  la URL en una pestana nueva del navegador.
- Codigo no existe al unirse: revisa mayusculas; el codigo no lleva
  0/O/1/I para no confundirse al dictarlo.
- GPS no graba: hace falta HTTPS (tu Traefik) y permiso de ubicacion;
  con pantalla apagada el navegador puede pausarlo. Para probar sin
  moverte: "Simular paseo".

NOTA DE FASES: esto es la 2A (viaje privado + ruta en vivo en el
servidor). La 2B hara que las fotos/sitios de todos se anadan en 2
toques y se vean en el mapa y muro comun del grupo; el Replay 3D tipo
God's Eye iria despues, probado aparte por rendimiento en el movil.
