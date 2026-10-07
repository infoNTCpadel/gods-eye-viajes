FROM nginx:alpine
COPY index.html manifest.json sw.js icon.svg icon-192.png icon-512.png /usr/share/nginx/html/
# SPA sencilla + cabeceras para PWA
RUN printf 'server{listen 80;server_name _;root /usr/share/nginx/html;index index.html;location /{try_files $uri $uri/ /index.html;}location = /sw.js{add_header Cache-Control "no-cache";}location = /manifest.json{add_header Cache-Control "no-cache";types{}default_type application/manifest+json;}}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80
