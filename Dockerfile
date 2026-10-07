FROM python:3-alpine
WORKDIR /app
COPY server.py index.html manifest.json sw.js icon.svg icon-192.png icon-512.png /app/
ENV DATA_DIR=/data PORT=80
EXPOSE 80
CMD ["python3", "server.py"]
