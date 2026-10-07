#!/usr/bin/env python3
"""God's Eye Viajes — Fase 2A: servidor ligero (solo stdlib).

Sirve los estaticos de la PWA y la API JSON de viajes privados con codigo.
SQLite en DATA_DIR/app.db (en Docker: /data, volumen persistente).
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
PORT = int(os.environ.get("PORT", "80"))
ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DATA_DIR, "app.db")
LOCK = threading.Lock()

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/1/I
MAX_BODY = 64 * 1024
MAX_BODY_PLACE = 2500 * 1024
PHOTOS_DIR = os.path.join(DATA_DIR, "photos")
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/manifest.json": ("manifest.json", "application/manifest+json"),
    "/sw.js": ("sw.js", "text/javascript"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
    "/favicon.ico": ("icon.svg", "image/svg+xml"),
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with LOCK, db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS trips(
              id TEXT PRIMARY KEY, name TEXT NOT NULL, from_date TEXT DEFAULT '',
              to_date TEXT DEFAULT '', invite_code TEXT UNIQUE NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS members(
              id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id),
              nickname TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
              token TEXT UNIQUE NOT NULL, device_id TEXT DEFAULT '',
              last_seen TEXT, last_lat REAL, last_lng REAL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS stops(
              id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id),
              name TEXT NOT NULL, cat TEXT DEFAULT 'peculiar', time TEXT DEFAULT '11:00',
              dur INTEGER DEFAULT 60, do_text TEXT DEFAULT '', lat REAL, lng REAL,
              done INTEGER DEFAULT 0, ord INTEGER DEFAULT 0, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS places(
              id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id),
              member_id TEXT DEFAULT '', author_nickname TEXT DEFAULT '',
              title TEXT DEFAULT '', cat TEXT DEFAULT 'peculiar', note TEXT DEFAULT '',
              info TEXT DEFAULT '', photo TEXT DEFAULT '', photo_path TEXT DEFAULT '',
              lat REAL, lng REAL, stop_id TEXT DEFAULT '',
              created_by TEXT DEFAULT '', created_at TEXT NOT NULL);
            """
        )
        # Migracion suave para BDs 2A ya creadas
        cols = {r["name"] for r in c.execute("PRAGMA table_info(places)")}
        for col, typ in (("member_id", "TEXT DEFAULT ''"), ("author_nickname", "TEXT DEFAULT ''"),
                         ("photo_path", "TEXT DEFAULT ''"), ("stop_id", "TEXT DEFAULT ''")):
            if col not in cols:
                c.execute("ALTER TABLE places ADD COLUMN %s %s" % (col, typ))


def new_code(c):
    import secrets

    for _ in range(50):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not c.execute("SELECT 1 FROM trips WHERE invite_code=?", (code,)).fetchone():
            return code
    raise RuntimeError("no se pudo generar codigo")


def trip_public(r):
    return {"id": r["id"], "name": r["name"], "inviteCode": r["invite_code"], "from": r["from_date"] or "", "to": r["to_date"] or ""}


def member_public(r):
    return {"id": r["id"], "nickname": r["nickname"], "role": r["role"], "lastSeen": r["last_seen"], "lastLat": r["last_lat"], "lastLng": r["last_lng"]}


def stop_public(r):
    return {"id": r["id"], "name": r["name"], "cat": r["cat"], "time": r["time"], "dur": r["dur"], "do": r["do_text"] or "", "lat": r["lat"], "lng": r["lng"], "done": bool(r["done"]), "ord": r["ord"]}


def place_public(r):
    keys = r.keys() if hasattr(r, "keys") else []
    photo_path = r["photo_path"] if "photo_path" in keys else ""
    photo_url = ""
    if photo_path:
        photo_url = "/api/photos/%s/%s" % (r["trip_id"], photo_path)
    author = ""
    if "author_nickname" in keys and r["author_nickname"]:
        author = r["author_nickname"]
    elif "created_by" in keys:
        author = r["created_by"] or ""
    return {
        "id": r["id"], "title": r["title"], "cat": r["cat"], "note": r["note"] or "",
        "info": r["info"] or "", "photo": "", "photoUrl": photo_url,
        "photoPath": photo_path or "",
        "lat": r["lat"], "lng": r["lng"],
        "stopId": (r["stop_id"] if "stop_id" in keys else "") or "",
        "author": author,
        "memberId": (r["member_id"] if "member_id" in keys else "") or "",
        "createdAt": r["created_at"],
    }


def trip_state(c, trip_row):
    stops = [stop_public(r) for r in c.execute("SELECT * FROM stops WHERE trip_id=? ORDER BY ord, created_at", (trip_row["id"],))]
    members = [member_public(r) for r in c.execute("SELECT * FROM members WHERE trip_id=? ORDER BY created_at", (trip_row["id"],))]
    places = [place_public(r) for r in c.execute("SELECT * FROM places WHERE trip_id=? ORDER BY created_at", (trip_row["id"],))]
    done = sum(1 for s in stops if s["done"])
    nxt = next((s for s in stops if not s["done"]), None)
    return {
        "trip": trip_public(trip_row),
        "members": members,
        "stops": stops,
        "places": places,
        "live": {"done": done, "total": len(stops), "nextStop": nxt, "progressPct": round(done * 100 / len(stops)) if stops else 0},
    }


def add_minutes(hhmm, mins):
    try:
        h, m = [int(x) for x in (hhmm or "11:00").split(":")]
    except Exception:
        h, m = 11, 0
    tot = (h * 60 + m + int(mins)) % 1440
    return "%02d:%02d" % (tot // 60, tot % 60)


def clean_str(v, maxlen, field):
    s = str(v or "").strip()
    if len(s) > maxlen:
        raise ValueError("%s demasiado largo" % field)
    return s


class H(BaseHTTPRequestHandler):
    server_version = "GodsEyeViajes/2B"

    def log_message(self, *a):
        pass

    # ---------- helpers ----------
    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def err(self, code, msg):
        self.send_json(code, {"ok": False, "error": msg})

    def read_json(self, limit=MAX_BODY):
        ln = int(self.headers.get("Content-Length") or 0)
        if ln > limit:
            raise ValueError("cuerpo demasiado grande")
        raw = self.rfile.read(ln) if ln else b"{}"
        try:
            return json.loads(raw.decode() or "{}")
        except Exception:
            raise ValueError("JSON invalido")

    def auth(self, trip_id=None):
        """Devuelve (member_row, trip_row) o manda 401/403 y devuelve None."""
        token = self.headers.get("X-Member-Token") or ""
        if not token:
            self.err(401, "falta X-Member-Token")
            return None
        with LOCK, db() as c:
            m = c.execute("SELECT * FROM members WHERE token=?", (token,)).fetchone()
            if not m:
                self.err(401, "token no valido")
                return None
            if trip_id and m["trip_id"] != trip_id:
                self.err(403, "ese token no pertenece a este viaje")
                return None
            t = c.execute("SELECT * FROM trips WHERE id=?", (m["trip_id"],)).fetchone()
            c.execute("UPDATE members SET last_seen=? WHERE id=?", (now_iso(), m["id"]))
            return dict(m), dict(t)

    # ---------- routing ----------
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/health":
            return self.send_json(200, {"ok": True})
        if p.startswith("/api/photos/"):
            return self.serve_photo(p)
        if p.startswith("/api/trips/by-code/"):
            return self.get_by_code(unquote(p.rsplit("/", 1)[-1]).upper())
        if p in STATIC:
            return self.serve_static(p)
        return self.err(404, "no encontrado")

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            if p == "/api/trips":
                return self.create_trip()
            if p == "/api/trips/join":
                return self.join_trip()
            parts = [x for x in p.split("/") if x]
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "stops":
                return self.create_stop(parts[2])
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "places":
                return self.create_place(parts[2])
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "heartbeat":
                return self.heartbeat(parts[2])
            return self.err(404, "no encontrado")
        except ValueError as e:
            return self.err(400, str(e))

    def do_PATCH(self):
        p = urlparse(self.path).path
        parts = [x for x in p.split("/") if x]
        try:
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "stops":
                return self.patch_stop(parts[2])
            return self.err(404, "no encontrado")
        except ValueError as e:
            return self.err(400, str(e))

    def do_DELETE(self):
        p = urlparse(self.path).path
        parts = [x for x in p.split("/") if x]
        try:
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "stops":
                return self.delete_stop(parts[2])
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "places":
                return self.delete_place(parts[2])
            return self.err(404, "no encontrado")
        except ValueError as e:
            return self.err(400, str(e))

    # ---------- endpoints ----------
    def create_trip(self):
        b = self.read_json()
        name = clean_str(b.get("name"), 80, "name")
        nick = clean_str(b.get("nickname"), 30, "nickname")
        if not name or not nick:
            return self.err(400, "name y nickname son obligatorios")
        tid, mid, token = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
        with LOCK, db() as c:
            code = new_code(c)
            c.execute(
                "INSERT INTO trips(id,name,from_date,to_date,invite_code,created_at) VALUES(?,?,?,?,?,?)",
                (tid, name, clean_str(b.get("from"), 20, "from"), clean_str(b.get("to"), 20, "to"), code, now_iso()),
            )
            c.execute(
                "INSERT INTO members(id,trip_id,nickname,role,token,device_id,last_seen,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (mid, tid, nick, "organizer", token, clean_str(b.get("deviceId"), 80, "deviceId"), now_iso(), now_iso()),
            )
            t = c.execute("SELECT * FROM trips WHERE id=?", (tid,)).fetchone()
            m = c.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
        self.send_json(201, {"ok": True, "trip": trip_public(t), "member": member_public(m), "memberToken": token})

    def join_trip(self):
        b = self.read_json()
        code = clean_str(b.get("code"), 12, "code").upper()
        nick = clean_str(b.get("nickname"), 30, "nickname")
        device = clean_str(b.get("deviceId"), 80, "deviceId")
        if not code or not nick:
            return self.err(400, "code y nickname son obligatorios")
        with LOCK, db() as c:
            t = c.execute("SELECT * FROM trips WHERE invite_code=?", (code,)).fetchone()
            if not t:
                return self.err(404, "codigo de viaje no existe")
            m = None
            if device:
                m = c.execute("SELECT * FROM members WHERE trip_id=? AND device_id=?", (t["id"], device)).fetchone()
            if m:
                token = m["token"]
                mid = m["id"]
                c.execute("UPDATE members SET last_seen=? WHERE id=?", (now_iso(), mid))
            else:
                mid, token = uuid.uuid4().hex, uuid.uuid4().hex
                c.execute(
                    "INSERT INTO members(id,trip_id,nickname,role,token,device_id,last_seen,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (mid, t["id"], nick, "member", token, device, now_iso(), now_iso()),
                )
            m = c.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
        self.send_json(200, {"ok": True, "trip": trip_public(t), "member": member_public(m), "memberToken": token})

    def get_by_code(self, code):
        a = self.auth()
        if not a:
            return
        m, t = a
        if (t["invite_code"] or "").upper() != code:
            return self.err(403, "ese token no pertenece a este viaje")
        with LOCK, db() as c:
            row = c.execute("SELECT * FROM trips WHERE id=?", (t["id"],)).fetchone()
            state = trip_state(c, row)
        self.send_json(200, {"ok": True, **state})

    def create_stop(self, trip_id):
        a = self.auth(trip_id)
        if not a:
            return
        m, _t = a
        if m["role"] != "organizer":
            return self.err(403, "solo el organizador puede anadir paradas")
        b = self.read_json()
        name = clean_str(b.get("name"), 90, "name")
        if not name:
            return self.err(400, "name obligatorio")
        with LOCK, db() as c:
            mx = c.execute("SELECT COALESCE(MAX(ord),-1) v FROM stops WHERE trip_id=?", (trip_id,)).fetchone()["v"]
            sid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO stops(id,trip_id,name,cat,time,dur,do_text,lat,lng,done,ord,created_at) VALUES(?,?,?,?,?,?,?,?,?,0,?,?)",
                (sid, trip_id, name, clean_str(b.get("cat"), 20, "cat") or "peculiar", clean_str(b.get("time"), 5, "time") or "11:00",
                 int(b.get("dur") or 60), clean_str(b.get("do"), 400, "do"), b.get("lat"), b.get("lng"), mx + 1, now_iso()),
            )
            s = c.execute("SELECT * FROM stops WHERE id=?", (sid,)).fetchone()
        self.send_json(201, {"ok": True, "stop": stop_public(s)})

    def patch_stop(self, stop_id):
        # primero localizar el viaje de la parada para validar pertenencia
        with LOCK, db() as c:
            s0 = c.execute("SELECT * FROM stops WHERE id=?", (stop_id,)).fetchone()
        if not s0:
            return self.err(404, "parada no existe")
        a = self.auth(s0["trip_id"])
        if not a:
            return
        m, _t = a
        b = self.read_json()
        organizer = m["role"] == "organizer"
        with LOCK, db() as c:
            s = c.execute("SELECT * FROM stops WHERE id=?", (stop_id,)).fetchone()
            if "done" in b:
                c.execute("UPDATE stops SET done=? WHERE id=?", (1 if b["done"] else 0, stop_id))
            elif "delayMinutes" in b:
                if not organizer:
                    return self.err(403, "solo el organizador puede retrasar la ruta")
                mins = int(b["delayMinutes"])
                rows = c.execute("SELECT id,time FROM stops WHERE trip_id=? AND ord>=? ORDER BY ord", (s["trip_id"], s["ord"])).fetchall()
                for r in rows:
                    c.execute("UPDATE stops SET time=? WHERE id=?", (add_minutes(r["time"], mins), r["id"]))
            elif "move" in b:
                if not organizer:
                    return self.err(403, "solo el organizador puede reordenar")
                d = 1 if int(b["move"]) > 0 else -1
                other = c.execute("SELECT * FROM stops WHERE trip_id=? AND ord=?", (s["trip_id"], s["ord"] + d)).fetchone()
                if other:
                    c.execute("UPDATE stops SET ord=? WHERE id=?", (other["ord"], s["id"]))
                    c.execute("UPDATE stops SET ord=? WHERE id=?", (s["ord"], other["id"]))
            else:
                if not organizer:
                    return self.err(403, "solo el organizador puede editar paradas")
                fields = {"name": ("name", 90), "cat": ("cat", 20), "time": ("time", 5), "dur": ("dur", None), "do": ("do_text", 400)}
                for k, (col, ml) in fields.items():
                    if k in b:
                        v = int(b[k]) if k == "dur" else clean_str(b[k], ml, k)
                        c.execute("UPDATE stops SET %s=? WHERE id=?" % col, (v, stop_id))
                if "lat" in b:
                    c.execute("UPDATE stops SET lat=? WHERE id=?", (b["lat"], stop_id))
                if "lng" in b:
                    c.execute("UPDATE stops SET lng=? WHERE id=?", (b["lng"], stop_id))
            s = c.execute("SELECT * FROM stops WHERE id=?", (stop_id,)).fetchone()
        self.send_json(200, {"ok": True, "stop": stop_public(s)})

    def delete_stop(self, stop_id):
        with LOCK, db() as c:
            s0 = c.execute("SELECT * FROM stops WHERE id=?", (stop_id,)).fetchone()
        if not s0:
            return self.err(404, "parada no existe")
        a = self.auth(s0["trip_id"])
        if not a:
            return
        m, _t = a
        if m["role"] != "organizer":
            return self.err(403, "solo el organizador puede borrar paradas")
        with LOCK, db() as c:
            c.execute("DELETE FROM stops WHERE id=?", (stop_id,))
        self.send_json(200, {"ok": True})

    def create_place(self, trip_id):
        a = self.auth(trip_id)
        if not a:
            return
        m, _t = a
        b = self.read_json(MAX_BODY_PLACE)
        title = clean_str(b.get("title"), 90, "title")
        if not title:
            return self.err(400, "title obligatorio")
        photo_path = ""
        photo = b.get("photo") or ""
        if photo:
            import base64

            if not isinstance(photo, str) or "," not in photo:
                return self.err(400, "foto invalida")
            try:
                raw = base64.b64decode(photo.split(",", 1)[1], validate=True)
            except Exception:
                return self.err(400, "foto invalida")
            if len(raw) > 2 * 1024 * 1024:
                return self.err(400, "foto demasiado grande")
            if len(raw) < 10:
                return self.err(400, "foto invalida")
            photo_path = uuid.uuid4().hex + ".jpg"
            dest_dir = os.path.join(PHOTOS_DIR, trip_id)
            os.makedirs(dest_dir, exist_ok=True)
            with open(os.path.join(dest_dir, photo_path), "wb") as f:
                f.write(raw)
        pid = uuid.uuid4().hex
        with LOCK, db() as c:
            c.execute(
                "INSERT INTO places(id,trip_id,member_id,author_nickname,title,cat,note,info,photo,photo_path,lat,lng,stop_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, trip_id, m["id"], m["nickname"], title,
                 clean_str(b.get("cat"), 20, "cat") or "peculiar",
                 clean_str(b.get("note"), 500, "note"), clean_str(b.get("info"), 800, "info"),
                 "", photo_path, b.get("lat"), b.get("lng"),
                 clean_str(b.get("stopId"), 80, "stopId"), m["nickname"], now_iso()),
            )
            r = c.execute("SELECT * FROM places WHERE id=?", (pid,)).fetchone()
        self.send_json(201, {"ok": True, "place": place_public(r)})

    def delete_place(self, place_id):
        with LOCK, db() as c:
            p0 = c.execute("SELECT * FROM places WHERE id=?", (place_id,)).fetchone()
        if not p0:
            return self.err(404, "lugar no existe")
        a = self.auth(p0["trip_id"])
        if not a:
            return
        m, _t = a
        is_author = ("member_id" in p0.keys() and p0["member_id"] == m["id"])
        if not is_author and m["role"] != "organizer":
            return self.err(403, "solo el autor o el organizador puede borrar este lugar")
        photo_path = p0["photo_path"] if "photo_path" in p0.keys() else ""
        with LOCK, db() as c:
            c.execute("DELETE FROM places WHERE id=?", (place_id,))
        if photo_path:
            try:
                os.remove(os.path.join(PHOTOS_DIR, p0["trip_id"], os.path.basename(photo_path)))
            except OSError:
                pass
        self.send_json(200, {"ok": True})

    def serve_photo(self, p):
        # /api/photos/<tripId>/<file> — sin token (URL con uuid no adivinable).
        # Anti path-traversal: solo basename y ruta resuelta dentro de PHOTOS_DIR.
        parts = [unquote(x) for x in p.split("/") if x]
        if len(parts) != 4 or parts[0] != "api" or parts[1] != "photos":
            return self.err(404, "no encontrado")
        trip_id, fname = parts[2], os.path.basename(parts[3])
        if not fname or fname != parts[3]:
            return self.err(404, "no encontrado")
        base = os.path.realpath(PHOTOS_DIR)
        path = os.path.realpath(os.path.join(base, trip_id, fname))
        if not path.startswith(base + os.sep) or not os.path.isfile(path):
            return self.err(404, "no encontrado")
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def heartbeat(self, trip_id):
        a = self.auth(trip_id)
        if not a:
            return
        m, _t = a
        try:
            b = self.read_json()
        except ValueError:
            b = {}
        with LOCK, db() as c:
            if b.get("lat") is not None and b.get("lng") is not None:
                c.execute("UPDATE members SET last_seen=?, last_lat=?, last_lng=? WHERE id=?", (now_iso(), b["lat"], b["lng"], m["id"]))
            else:
                c.execute("UPDATE members SET last_seen=? WHERE id=?", (now_iso(), m["id"]))
        self.send_json(200, {"ok": True})

    def serve_static(self, p):
        name, ctype = STATIC[p]
        path = os.path.join(ROOT, name)
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            return self.err(404, "no encontrado")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if name in ("sw.js", "manifest.json", "index.html"):
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    init_db()
    print("Gods Eye Viajes 2B en :%d DATA_DIR=%s" % (PORT, DATA_DIR), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
