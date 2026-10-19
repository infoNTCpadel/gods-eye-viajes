#!/usr/bin/env python3
"""God's Eye Viajes — Pivote: diario de viajes con companeros (uso personal).

Tres piezas: Diario (fotos por dias), Gastos (reparto entre companeros),
Donde estamos (localizador con interruptor de privacidad).
Solo stdlib. SQLite en DATA_DIR/app.db (en Docker: /data, volumen persistente).
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
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


def parse_dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        return None


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
              last_seen TEXT, last_lat REAL, last_lng REAL,
              sharing_until TEXT DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS expenses(
              id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id),
              member_id TEXT DEFAULT '', payer_nickname TEXT NOT NULL,
              description TEXT DEFAULT '', amount_cents INTEGER NOT NULL,
              currency TEXT DEFAULT 'EUR', split_mode TEXT DEFAULT 'equal',
              participants_json TEXT DEFAULT '[]', photo_path TEXT DEFAULT '',
              created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settlements(
              id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id),
              member_id TEXT DEFAULT '', from_nickname TEXT NOT NULL,
              to_nickname TEXT NOT NULL, amount_cents INTEGER NOT NULL,
              created_at TEXT NOT NULL);
            """
        )
        # Migraciones suaves (tablas de versiones anteriores)
        mcols = {r["name"] for r in c.execute("PRAGMA table_info(members)")}
        if "sharing_until" not in mcols:
            c.execute("ALTER TABLE members ADD COLUMN sharing_until TEXT DEFAULT ''")
        ecols = {r["name"] for r in c.execute("PRAGMA table_info(expenses)")}
        for col, typ in (("currency", "TEXT DEFAULT 'EUR'"), ("split_mode", "TEXT DEFAULT 'equal'"),
                         ("participants_json", "TEXT DEFAULT '[]'"), ("photo_path", "TEXT DEFAULT ''"),
                         ("kind", "TEXT DEFAULT 'expense'"), ("from_pot", "INTEGER DEFAULT 0")):
            if col not in ecols:
                c.execute("ALTER TABLE expenses ADD COLUMN %s %s" % (col, typ))
        tcols = {r["name"] for r in c.execute("PRAGMA table_info(trips)")}
        if "treasurer_member_id" not in tcols:
            c.execute("ALTER TABLE trips ADD COLUMN treasurer_member_id TEXT DEFAULT ''")


def new_code(c):
    import secrets

    for _ in range(50):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if not c.execute("SELECT 1 FROM trips WHERE invite_code=?", (code,)).fetchone():
            return code
    raise RuntimeError("no se pudo generar codigo")


def money(cents):
    return "%.2f \u20ac" % (cents / 100.0)


def trip_public(r):
    return {"id": r["id"], "name": r["name"], "inviteCode": r["invite_code"], "from": r["from_date"] or "", "to": r["to_date"] or ""}


def member_sharing(r):
    """(activa, minutos_restantes). Sin compartir -> (False, 0)."""
    until = parse_dt(r["sharing_until"]) if "sharing_until" in r.keys() else None
    if not until:
        return False, 0
    left = int((until - datetime.now(timezone.utc)).total_seconds() // 60)
    return left >= 0, max(0, left)


def member_public(r, for_expense=False):
    active, left = member_sharing(r)
    out = {"id": r["id"], "nickname": r["nickname"], "role": r["role"], "lastSeen": r["last_seen"]}
    if for_expense:
        return out
    out["sharing"] = active
    out["sharingLeftMin"] = left
    # La posicion solo se expone mientras el sharing esta activo y no caducado
    out["lastLat"] = r["last_lat"] if active else None
    out["lastLng"] = r["last_lng"] if active else None
    return out


def place_public(r):
    keys = r.keys() if hasattr(r, "keys") else []
    photo_path = r["photo_path"] if "photo_path" in keys else ""
    photo_url = "/api/photos/%s/%s" % (r["trip_id"], photo_path) if photo_path else ""
    author = r["author_nickname"] if "author_nickname" in keys and r["author_nickname"] else (r["created_by"] if "created_by" in keys and r["created_by"] else "")
    return {
        "id": r["id"], "title": r["title"], "cat": r["cat"], "note": r["note"] or "",
        "info": r["info"] or "", "photoUrl": photo_url, "photoPath": photo_path or "",
        "lat": r["lat"], "lng": r["lng"],
        "stopId": (r["stop_id"] if "stop_id" in keys else "") or "",
        "author": author or "", "memberId": (r["member_id"] if "member_id" in keys else "") or "",
        "createdAt": r["created_at"],
    }


def expense_public(r):
    try:
        parts = json.loads(r["participants_json"] or "[]")
    except Exception:
        parts = []
    keys = r.keys() if hasattr(r, "keys") else []
    return {
        "id": r["id"], "payer": r["payer_nickname"], "description": r["description"] or "",
        "amountCents": r["amount_cents"], "amount": money(r["amount_cents"]),
        "splitMode": r["split_mode"] or "equal", "parts": parts,
        "kind": (r["kind"] if "kind" in keys and r["kind"] else "expense"),
        "fromPot": bool(r["from_pot"]) if "from_pot" in keys else False,
        "photoUrl": ("/api/photos/%s/%s" % (r["trip_id"], r["photo_path"]) if r["photo_path"] else ""),
        "authorMemberId": r["member_id"] or "", "createdAt": r["created_at"],
    }


def settlement_public(r):
    return {
        "id": r["id"], "from": r["from_nickname"], "to": r["to_nickname"],
        "amountCents": r["amount_cents"], "amount": money(r["amount_cents"]),
        "authorMemberId": r["member_id"] or "", "createdAt": r["created_at"],
    }


def compute_balances(expenses, settlements, nicknames):
    """Balance por persona: positivo = le deben, negativo = debe."""
    paid = {n: 0 for n in nicknames}
    owed = {n: 0 for n in nicknames}
    for e in expenses:
        paid[e["payer"]] = paid.get(e["payer"], 0) + e["amountCents"]
        for p in e["parts"]:
            owed[p["nickname"]] = owed.get(p["nickname"], 0) + p["cents"]
    # Los pagos registrados reducen la deuda del pagador y el credito del receptor
    for s in settlements:
        owed[s["from"]] = owed.get(s["from"], 0) - s["amountCents"]
        paid[s["to"]] = paid.get(s["to"], 0) - s["amountCents"]
    nets = {n: paid.get(n, 0) - owed.get(n, 0) for n in nicknames}
    return paid, owed, nets


def who_pays_whom(nets):
    """Simplificacion greedy: minimo de pagos deudores -> acreedores."""
    debtors = [[n, -v] for n, v in nets.items() if v < 0]
    creditors = [[n, v] for n, v in nets.items() if v > 0]
    debtors.sort(key=lambda x: x[1])
    creditors.sort(key=lambda x: x[1])
    out = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        dn, da = debtors[i]
        cn, ca = creditors[j]
        x = min(da, ca)
        out.append({"from": dn, "to": cn, "amountCents": int(round(x)), "amount": money(int(round(x)))})
        da -= x
        ca -= x
        if da < 0.5:
            i += 1
        else:
            debtors[i][1] = da
        if ca < 0.5:
            j += 1
        else:
            creditors[j][1] = ca
    return out


def get_treasurer(c, trip_id):
    """Devuelve (member_id, nickname) del tesorero o ('','') si no hay."""
    row = c.execute("SELECT treasurer_member_id FROM trips WHERE id=?", (trip_id,)).fetchone()
    mid = (row["treasurer_member_id"] if row and "treasurer_member_id" in row.keys() else "") or ""
    if not mid:
        return "", ""
    m = c.execute("SELECT nickname FROM members WHERE id=?", (mid,)).fetchone()
    return mid, (m["nickname"] if m else "")


def trip_state(c, trip_row):
    members = [member_public(r) for r in c.execute("SELECT * FROM members WHERE trip_id=? ORDER BY created_at", (trip_row["id"],))]
    places = []
    try:
        places = [place_public(r) for r in c.execute("SELECT * FROM places WHERE trip_id=? ORDER BY created_at", (trip_row["id"],))]
    except Exception:
        pass
    expenses = [expense_public(r) for r in c.execute("SELECT * FROM expenses WHERE trip_id=? ORDER BY created_at", (trip_row["id"],))]
    settlements = [settlement_public(r) for r in c.execute("SELECT * FROM settlements WHERE trip_id=? ORDER BY created_at", (trip_row["id"],))]
    nicknames = [m["nickname"] for m in members]
    paid, owed, nets = compute_balances(expenses, settlements, nicknames)
    balances = [{"nickname": n, "paidCents": paid[n], "paid": money(paid[n]),
                 "shareCents": owed[n], "share": money(owed[n]),
                 "balanceCents": nets[n], "balance": money(abs(nets[n]))} for n in nicknames]
    _tmid, treasurer_nick = get_treasurer(c, trip_row["id"])
    contributed = sum(e["amountCents"] for e in expenses if e["kind"] == "contribution")
    spent_pot = sum(e["amountCents"] for e in expenses if e["fromPot"])
    pot = {
        "treasurer": treasurer_nick,
        "contributedCents": contributed, "contributed": money(contributed),
        "spentFromPotCents": spent_pot, "spentFromPot": money(spent_pot),
        "remainingCents": contributed - spent_pot, "remaining": money(contributed - spent_pot),
    }
    return {
        "trip": trip_public(trip_row),
        "members": members,
        "places": places,
        "expenses": expenses,
        "settlements": settlements,
        "balances": balances,
        "whoPaysWhom": who_pays_whom(nets),
        "pot": pot,
    }


def clean_str(v, maxlen, field):
    s = str(v or "").strip()
    if len(s) > maxlen:
        raise ValueError("%s demasiado largo" % field)
    return s


def save_photo_b64(photo, trip_id, limit=2 * 1024 * 1024):
    """Decodifica dataURL y la guarda. Devuelve el nombre de fichero o ''."""
    if not photo:
        return ""
    import base64

    if not isinstance(photo, str) or "," not in photo:
        raise ValueError("foto invalida")
    try:
        raw = base64.b64decode(photo.split(",", 1)[1], validate=True)
    except Exception:
        raise ValueError("foto invalida")
    if len(raw) > limit or len(raw) < 10:
        raise ValueError("foto invalida")
    photo_path = uuid.uuid4().hex + ".jpg"
    dest_dir = os.path.join(PHOTOS_DIR, trip_id)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, photo_path), "wb") as f:
        f.write(raw)
    return photo_path


class H(BaseHTTPRequestHandler):
    server_version = "GodsEyeViajes/pivote-diario"

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
        parts = [x for x in p.split("/") if x]
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "balances":
            return self.get_balances(parts[2])
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
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "places":
                return self.create_place(parts[2])
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "heartbeat":
                return self.heartbeat(parts[2])
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "expenses":
                return self.create_expense(parts[2])
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "settlements":
                return self.create_settlement(parts[2])
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "treasurer":
                return self.set_treasurer(parts[2])
            if len(parts) == 5 and parts[0] == "api" and parts[1] == "trips" and parts[3] == "pot" and parts[4] == "contribute":
                return self.pot_contribute(parts[2])
            return self.err(404, "no encontrado")
        except ValueError as e:
            return self.err(400, str(e))

    def do_DELETE(self):
        p = urlparse(self.path).path
        parts = [x for x in p.split("/") if x]
        try:
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "places":
                return self.delete_place(parts[2])
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "expenses":
                return self.delete_expense(parts[2])
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
        self.send_json(201, {"ok": True, "trip": trip_public(t), "member": member_public(m, True), "memberToken": token})

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
        self.send_json(200, {"ok": True, "trip": trip_public(t), "member": member_public(m, True), "memberToken": token})

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

    def get_balances(self, trip_id):
        a = self.auth(trip_id)
        if not a:
            return
        _m, t = a
        with LOCK, db() as c:
            row = c.execute("SELECT * FROM trips WHERE id=?", (t["id"],)).fetchone()
            members = [member_public(r, True) for r in c.execute("SELECT * FROM members WHERE trip_id=? ORDER BY created_at", (t["id"],))]
            expenses = [expense_public(r) for r in c.execute("SELECT * FROM expenses WHERE trip_id=? ORDER BY created_at", (t["id"],))]
            settlements = [settlement_public(r) for r in c.execute("SELECT * FROM settlements WHERE trip_id=? ORDER BY created_at", (t["id"],))]
            nicknames = [m["nickname"] for m in members]
            paid, owed, nets = compute_balances(expenses, settlements, nicknames)
            balances = [{"nickname": n, "paidCents": paid[n], "paid": money(paid[n]),
                         "shareCents": owed[n], "share": money(owed[n]),
                         "balanceCents": nets[n], "balance": money(abs(nets[n]))} for n in nicknames]
            self.send_json(200, {"ok": True, "balances": balances, "whoPaysWhom": who_pays_whom(nets),
                                 "expenses": len(expenses), "settlements": len(settlements)})

    def create_place(self, trip_id):
        a = self.auth(trip_id)
        if not a:
            return
        m, _t = a
        b = self.read_json(MAX_BODY_PLACE)
        title = clean_str(b.get("title"), 90, "title")
        if not title:
            return self.err(400, "title obligatorio")
        photo_path = save_photo_b64(b.get("photo") or "", trip_id)
        pid = uuid.uuid4().hex
        with LOCK, db() as c:
            # places puede no existir en instalaciones muy antiguas
            c.execute(
                """CREATE TABLE IF NOT EXISTS places(
                id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id),
                member_id TEXT DEFAULT '', author_nickname TEXT DEFAULT '',
                title TEXT DEFAULT '', cat TEXT DEFAULT 'peculiar', note TEXT DEFAULT '',
                info TEXT DEFAULT '', photo TEXT DEFAULT '', photo_path TEXT DEFAULT '',
                lat REAL, lng REAL, stop_id TEXT DEFAULT '',
                created_by TEXT DEFAULT '', created_at TEXT NOT NULL)"""
            )
            c.execute(
                "INSERT INTO places(id,trip_id,member_id,author_nickname,title,cat,note,info,photo,photo_path,lat,lng,stop_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, trip_id, m["id"], m["nickname"], title, "peculiar",
                 clean_str(b.get("note"), 500, "note"), "", "", photo_path,
                 b.get("lat"), b.get("lng"), "", m["nickname"], now_iso()),
            )
            r = c.execute("SELECT * FROM places WHERE id=?", (pid,)).fetchone()
        self.send_json(201, {"ok": True, "place": place_public(r)})

    def delete_place(self, place_id):
        with LOCK, db() as c:
            try:
                p0 = c.execute("SELECT * FROM places WHERE id=?", (place_id,)).fetchone()
            except Exception:
                return self.err(404, "lugar no existe")
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

    # ---------- GASTOS ----------
    def member_nicks(self, c, trip_id):
        return {r["nickname"] for r in c.execute("SELECT nickname FROM members WHERE trip_id=?", (trip_id,))}

    def split_equal(self, total, nicks):
        base = total // len(nicks)
        rem = total - base * len(nicks)
        return [{"nickname": n, "cents": base + (1 if i < rem else 0)} for i, n in enumerate(nicks)]

    def create_expense(self, trip_id):
        a = self.auth(trip_id)
        if not a:
            return
        m, _t = a
        b = self.read_json(MAX_BODY_PLACE)
        try:
            total = int(round(float(b.get("amount") or 0) * 100))
        except Exception:
            return self.err(400, "importe invalido")
        if total <= 0:
            return self.err(400, "el importe tiene que ser mayor que 0")
        payer_raw = clean_str(b.get("payer"), 30, "payer")
        from_pot = 1 if b.get("from_pot") else 0
        mode = clean_str(b.get("split_mode"), 12, "split_mode") or "equal"
        if mode not in ("equal", "amounts", "shares"):
            return self.err(400, "split_mode invalido")
        raw_parts = b.get("participants") or []
        if not isinstance(raw_parts, list) or not raw_parts:
            return self.err(400, "elige quien participa en el gasto")
        with LOCK, db() as c:
            nicks = self.member_nicks(c, trip_id)
            _tmid, treasurer_nick = get_treasurer(c, trip_id)
            if from_pot and not treasurer_nick:
                return self.err(400, "designa primero quién lleva el bote")
            payer = payer_raw or (treasurer_nick if from_pot else "")
            if payer not in nicks:
                return self.err(400, "quien paga tiene que ser del viaje")
            pn = []
            for p in raw_parts:
                n = clean_str((p or {}).get("nickname"), 30, "nickname")
                if n not in nicks:
                    return self.err(400, "participante no es del viaje: " + n)
                if n in [x["nickname"] for x in pn]:
                    return self.err(400, "participante duplicado: " + n)
                pn.append({"nickname": n, "raw": p or {}})
            if mode == "equal":
                parts = self.split_equal(total, [x["nickname"] for x in pn])
            elif mode == "amounts":
                vals = []
                for x in pn:
                    try:
                        vals.append(int(round(float(x["raw"].get("amount") or 0) * 100)))
                    except Exception:
                        return self.err(400, "cantidad invalida para " + x["nickname"])
                if any(v < 0 for v in vals) or sum(vals) <= 0:
                    return self.err(400, "cantidades invalidas")
                diff = total - sum(vals)
                vals[0] += diff  # ajusta el redondeo en el primero
                parts = [{"nickname": x["nickname"], "cents": v} for x, v in zip(pn, vals)]
            else:  # shares
                vals = []
                for x in pn:
                    try:
                        s = float(x["raw"].get("share") or 0)
                    except Exception:
                        return self.err(400, "participacion invalida para " + x["nickname"])
                    if s <= 0:
                        return self.err(400, "participacion invalida para " + x["nickname"])
                    vals.append(s)
                tot_s = sum(vals)
                raw_c = [total * s / tot_s for s in vals]
                floor = [int(v) for v in raw_c]
                rem = total - sum(floor)
                order = sorted(range(len(vals)), key=lambda i: raw_c[i] - floor[i], reverse=True)
                for i in order[:rem]:
                    floor[i] += 1
                parts = [{"nickname": x["nickname"], "cents": v, "share": s} for x, v, s in zip(pn, floor, vals)]
            photo_path = save_photo_b64(b.get("photo") or "", trip_id)
            eid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO expenses(id,trip_id,member_id,payer_nickname,description,amount_cents,currency,split_mode,participants_json,kind,from_pot,photo_path,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eid, trip_id, m["id"], payer, clean_str(b.get("description"), 90, "description") or "Gasto",
                 total, clean_str(b.get("currency"), 3, "currency") or "EUR", mode,
                 json.dumps(parts, ensure_ascii=False), "expense", from_pot, photo_path, now_iso()),
            )
            r = c.execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone()
        self.send_json(201, {"ok": True, "expense": expense_public(r)})

    def delete_expense(self, expense_id):
        with LOCK, db() as c:
            e0 = c.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
        if not e0:
            return self.err(404, "gasto no existe")
        a = self.auth(e0["trip_id"])
        if not a:
            return
        m, _t = a
        if e0["member_id"] != m["id"] and m["role"] != "organizer":
            return self.err(403, "solo quien lo registro o el organizador puede borrarlo")
        with LOCK, db() as c:
            c.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        self.send_json(200, {"ok": True})

    def create_settlement(self, trip_id):
        a = self.auth(trip_id)
        if not a:
            return
        m, _t = a
        b = self.read_json()
        try:
            cents = int(round(float(b.get("amount") or 0) * 100))
        except Exception:
            return self.err(400, "importe invalido")
        if cents <= 0:
            return self.err(400, "el importe tiene que ser mayor que 0")
        frm = clean_str(b.get("from"), 30, "from")
        to = clean_str(b.get("to"), 30, "to")
        if not frm or not to or frm == to:
            return self.err(400, "from y to tienen que ser dos companeros distintos")
        with LOCK, db() as c:
            nicks = self.member_nicks(c, trip_id)
            if frm not in nicks or to not in nicks:
                return self.err(400, "from/to tienen que ser del viaje")
            sid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO settlements(id,trip_id,member_id,from_nickname,to_nickname,amount_cents,created_at) VALUES(?,?,?,?,?,?,?)",
                (sid, trip_id, m["id"], frm, to, cents, now_iso()),
            )
            r = c.execute("SELECT * FROM settlements WHERE id=?", (sid,)).fetchone()
        self.send_json(201, {"ok": True, "settlement": settlement_public(r)})

    def set_treasurer(self, trip_id):
        """Designa o cambia quien lleva el bote. Cualquier miembro (confianza)."""
        a = self.auth(trip_id)
        if not a:
            return
        _m, _t = a
        b = self.read_json()
        nick = clean_str(b.get("nickname"), 30, "nickname")
        with LOCK, db() as c:
            if nick:
                r = c.execute("SELECT id, nickname FROM members WHERE trip_id=? AND nickname=?",
                              (trip_id, nick)).fetchone()
                if not r:
                    return self.err(400, "ese apodo no es del viaje")
                c.execute("UPDATE trips SET treasurer_member_id=? WHERE id=?", (r["id"], trip_id))
                out = r["nickname"]
            else:
                c.execute("UPDATE trips SET treasurer_member_id='' WHERE id=?", (trip_id,))
                out = ""
        self.send_json(200, {"ok": True, "treasurer": out})

    def pot_contribute(self, trip_id):
        """Aportacion al bote: la crea como expense kind=contribution, participants=[tesorero]."""
        a = self.auth(trip_id)
        if not a:
            return
        m, _t = a
        b = self.read_json()
        try:
            total = int(round(float(b.get("amount") or 0) * 100))
        except Exception:
            return self.err(400, "importe invalido")
        if total <= 0:
            return self.err(400, "el importe tiene que ser mayor que 0")
        nick = clean_str(b.get("nickname"), 30, "nickname") or m["nickname"]
        with LOCK, db() as c:
            nicks = self.member_nicks(c, trip_id)
            if nick not in nicks:
                return self.err(400, "quien aporta tiene que ser del viaje")
            _tmid, treasurer_nick = get_treasurer(c, trip_id)
            if not treasurer_nick:
                return self.err(400, "designa primero quién lleva el bote")
            eid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO expenses(id,trip_id,member_id,payer_nickname,description,amount_cents,currency,split_mode,participants_json,kind,from_pot,photo_path,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eid, trip_id, m["id"], nick, "Aportación al bote de " + nick, total, "EUR", "equal",
                 json.dumps([{"nickname": treasurer_nick, "cents": total}], ensure_ascii=False),
                 "contribution", 0, "", now_iso()),
            )
            r = c.execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone()
        self.send_json(201, {"ok": True, "expense": expense_public(r)})

    def serve_photo(self, p):
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
        lat, lng = b.get("lat"), b.get("lng")
        sharing = bool(b.get("sharing"))
        with LOCK, db() as c:
            if sharing and lat is not None and lng is not None:
                mins = int(b.get("sharingMinutes") or 60)
                mins = max(1, min(mins, 8 * 60))
                until = (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()
                c.execute("UPDATE members SET last_seen=?, last_lat=?, last_lng=?, sharing_until=? WHERE id=?",
                          (now_iso(), lat, lng, until, m["id"]))
            else:
                # Sin compartir: NO se guarda ni se expone ninguna posicion
                c.execute("UPDATE members SET last_seen=?, last_lat=NULL, last_lng=NULL, sharing_until=NULL WHERE id=?",
                          (now_iso(), m["id"]))
        self.send_json(200, {"ok": True, "sharing": sharing and lat is not None and lng is not None})

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
    print("Gods Eye Viajes (diario) en :%d DATA_DIR=%s" % (PORT, DATA_DIR), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
