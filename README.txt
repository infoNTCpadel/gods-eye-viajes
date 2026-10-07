GOD'S EYE VIAJES — Fase 1 (PWA para tu VPS)
==============================================

Que es: app de viaje generica God's Eye (oscuro tierra/oro). El mapa se
revela con tu trazo dorado, ruta del organizador compartible por enlace
de WhatsApp (sin servidor), lugares/fotos guardados en el movil.
Sin backend, sin cuentas, sin claves. Todo queda en el navegador de
cada movil (localStorage). Dominio por defecto: viajes.ntcpadel.com

ANTES DE DESPLEGAR (2 min)
----------------------------
1) Registro DNS A: crea un registro A de "viajes" en ntcpadel.com
   apuntando a la IP publica de tu VPS. Espera a que resuelva:
   en el VPS:  getent hosts viajes.ntcpadel.com
   Si prefieres otro dominio, cambia DOMAIN en el .env (paso 3).
2) Red de Traefik: tu Traefik solo enruta contenedores que comparten
   su red. Averigua cual es:
     docker network ls
     docker inspect <contenedor-traefik> --format '{{json .NetworkSettings.Networks}}'
   Pon ese nombre en TRAEFIK_NETWORK del .env (por defecto: web).
   En la PWA de knbacademy no hizo falta porque ya compartian red;
   aqui, si Traefik no ve el contenedor, es por la red.

DESPLIEGUE EN EL VPS (en /opt/gods-eye-viajes)
----------------------------------------------
Desde el movil con tu cliente SSH, o desde una terminal:
  1. Sube el zip al VPS y descomprimelo (crea la carpeta sola):
       cd /opt && unzip gods-eye-viajes-vps-v1.zip
       cd /opt/gods-eye-viajes-vps
     Dentro deben estar juntos:
     index.html  manifest.json  sw.js  icon.svg  icon-*.png
     Dockerfile  docker-compose.yml  .env.example  README.txt
  2. cp .env.example .env  y edita DOMAIN (y TRAEFIK_NETWORK si toca).
  3. docker compose up -d --build
  4. Comprueba:  docker ps | grep gods-eye  y  docker logs gods-eye-viajes
  5. Abre https://viajes.ntcpadel.com en el movil.
     Menu del navegador -> "Anadir a pantalla de inicio" (queda como app).

COMO PROBARLO EN 2 MINUTOS (sin salir de casa)
----------------------------------------------
  1. "Crear viaje": nombre y fechas. Apunta el codigo local.
  2. Organizer: anade 2 paradas (bodega 11:00, pueblo 13:30), con su
     "que hacer". Prueba "↑/↓", "+20 min retraso" y "✓ Hecho".
     "Ahora toca" debe mostrar la primera sin hacer.
  3. Pulsa "Compartir ruta": se genera un enlace ?ruta=... (copiado) y
     se abre WhatsApp. Envialo a un amigo: al abrirlo importa la ruta.
  4. Pulsa "Simular paseo": veras dibujarse el trazo dorado sin GPS.
     Luego "Grabar" con GPS real cuando salgas a andar.
  5. Anade un "Lugar": mueve el mapa, titulo, nota, foto (vino/monumento),
     pega la "info recabada" de internet. Queda pin y tarjeta.
  6. "Replay God's Eye": sobrevuela el recorrido en ~10 s y cierra con
     la tarjeta del viaje (km, paradas, lugares). Captura para compartir.

SI ALGO FALLA (Traefik 404 / no abre)
-------------------------------------
- 404 de Traefik: contenedor y Traefik no comparten red. Revisa
  TRAEFIK_NETWORK en .env y vuelve a "docker compose up -d". Confirma
  con: docker inspect gods-eye-viajes --format '{{json .NetworkSettings.Networks}}'
- Certificado no emitido: el registro A aun no resuelve o el dominio
  no coincide con Host() (label en docker-compose.yml usa $DOMAIN).
- La app abre pero sin mapa: necesitas internet para Leaflet/mapa; la
  PWA cachea la app, no las teselas del mapa.
- GPS no graba: en iOS/Android el GPS en el navegador exige HTTPS y
  permiso de ubicacion; con pantalla apagada puede pausarse. Solucion
  del piloto: pantalla encendida en el bolsillo o "Simular" para probar.
  La version nativa (si el piloto valida) resuelve el segundo plano.
- Fotos "desaparecen": estan en el localStorage de ESE navegador/movil.
  No hay copia en servidor: exporta con capturas y el enlace de ruta.
  Limite practico ~5 MB por movil (la app avisa y comprime a 900 px).

NOTA: es Fase 1 estatica a proposito: sin backend no hay mapa comun en
vivo entre moviles. Cada amigo importa la ruta del organizador y revela
su propio trazo; el Replay y las tarjetas se comparten por WhatsApp.
Si el viaje valida el concepto, la Fase 2 anade servidor minimo en el
mismo VPS para sincronizar grupo en tiempo real.
