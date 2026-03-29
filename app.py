from rag import build_structured_context
from llm import LLMClient
from models import db, User, Species, MuseumDoc, Visit, ChatTurn, QRStyle
import docx
from PyPDF2 import PdfReader
from sqlalchemy import or_, text
from io import BytesIO
from PIL import Image, ImageColor, ImageDraw, ImageFont
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
try:
    from qrcode.image.styles.moduledrawers.pil import (
        SquareModuleDrawer, RoundedModuleDrawer, CircleModuleDrawer, GappedSquareModuleDrawer,
    )
except ImportError:
    from qrcode.image.styles.moduledrawers import (
        SquareModuleDrawer, RoundedModuleDrawer, CircleModuleDrawer, GappedSquareModuleDrawer,
    )

from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask import Flask, render_template, redirect, url_for, request, abort, jsonify, flash, Response, stream_with_context
import requests
import urllib.parse
import uuid
import re
import os
from dotenv import load_dotenv

load_dotenv()


ID_RE = re.compile(r"^[a-z0-9-_]+$")

ALLOWED_DOCS = {"pdf", "docx", "txt"}
ALLOWED_AUDIO = {"mp3"}
ALLOWED_IMAGES = {"jpg", "jpeg", "png", "webp"}

UPLOAD_DIR = os.path.join("static", "uploads")


def sanitize_id(raw: str) -> str:
    if raw is None:
        return ""
    sid = raw.strip().lower()
    sid = re.sub(r"[^a-z0-9-_]", "", sid)
    return sid


def ext_of(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()


def wikipedia_summary_es(title: str) -> str:
    if not title:
        return ""
    t = urllib.parse.quote(title)
    url = f"https://es.wikipedia.org/api/rest_v1/page/summary/{t}"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            return ""
        data = r.json()
        return (data.get("extract") or "").strip()
    except Exception:
        return ""


def allowed(filename: str, allowed_set: set[str]) -> bool:
    return ext_of(filename) in allowed_set


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def unique_name(prefix: str, filename: str) -> str:
    safe = secure_filename(filename)
    return f"{prefix}_{uuid.uuid4().hex}_{safe}"


QR_FRAME_OPTIONS = {
    "simple": "Simple",
    "card": "Tarjeta",
    "badge": "Insignia",
    "scanme": "Scan me",
}

QR_MODULE_OPTIONS = {
    "square": "Cuadrado",
    "rounded": "Redondeado",
    "circle": "Circular",
    "gapped": "Separado",
}


def clamp_int(raw, min_value: int, max_value: int, default: int) -> int:
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, value))


def normalize_hex_color(raw: str | None, default: str) -> str:
    value = (raw or "").strip()
    if re.fullmatch(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})", value):
        return value
    return default


def parse_bool(raw, default: bool) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "on", "yes", "y"}


def get_qr_defaults(species: Species) -> dict:
    return {
        "frame_style": "simple",
        "module_style": "square",
        "fill_color": "#111827",
        "back_color": "#ffffff",
        "accent_color": "#059669",
        "label_text": "",
        "top_text": "BioScan",
        "show_top_text": True,
        "show_label_text": True,
        "top_text_size": 18,
        "label_text_size": 18,
        "box_size": 10,
        "border": 4,
    }


def get_qr_style_dict(species: Species, style_obj: QRStyle | None = None, overrides=None) -> dict:
    data = get_qr_defaults(species)
    if style_obj:
        data.update({
            "frame_style": style_obj.frame_style or data["frame_style"],
            "module_style": style_obj.module_style or data["module_style"],
            "fill_color": style_obj.fill_color or data["fill_color"],
            "back_color": style_obj.back_color or data["back_color"],
            "accent_color": style_obj.accent_color or data["accent_color"],
            "label_text": style_obj.label_text if style_obj.label_text is not None else "",
            "top_text": style_obj.top_text if style_obj.top_text is not None else data["top_text"],
            "show_top_text": bool(style_obj.show_top_text) if style_obj.show_top_text is not None else data["show_top_text"],
            "show_label_text": bool(style_obj.show_label_text) if style_obj.show_label_text is not None else data["show_label_text"],
            "top_text_size": style_obj.top_text_size or data["top_text_size"],
            "label_text_size": style_obj.label_text_size or data["label_text_size"],
            "box_size": style_obj.box_size or data["box_size"],
            "border": style_obj.border or data["border"],
        })

    source = overrides or {}
    if hasattr(source, "get"):
        is_multi_dict = hasattr(source, "getlist")
        frame_style = (source.get("frame_style")
                       or data["frame_style"]).strip()
        module_style = (source.get("module_style")
                        or data["module_style"]).strip()
        data["frame_style"] = frame_style if frame_style in QR_FRAME_OPTIONS else data["frame_style"]
        data["module_style"] = module_style if module_style in QR_MODULE_OPTIONS else data["module_style"]
        data["fill_color"] = normalize_hex_color(
            source.get("fill_color"), data["fill_color"])
        data["back_color"] = normalize_hex_color(
            source.get("back_color"), data["back_color"])
        data["accent_color"] = normalize_hex_color(
            source.get("accent_color"), data["accent_color"])
        raw_label_text = source.get("label_text")
        data["label_text"] = str(
            raw_label_text if raw_label_text is not None else data["label_text"]
        )[:160].strip()

        raw_top_text = source.get("top_text")
        data["top_text"] = str(
            raw_top_text if raw_top_text is not None else data["top_text"]
        )[:80].strip()

        if is_multi_dict:
            data["show_top_text"] = parse_bool(source.get("show_top_text"), False)
            data["show_label_text"] = parse_bool(source.get("show_label_text"), False)
        else:
            if "show_top_text" in source:
                data["show_top_text"] = parse_bool(
                    source.get("show_top_text"), data["show_top_text"])
            if "show_label_text" in source:
                data["show_label_text"] = parse_bool(
                    source.get("show_label_text"), data["show_label_text"])

        data["top_text_size"] = clamp_int(source.get(
            "top_text_size"), 10, 52, data["top_text_size"])
        data["label_text_size"] = clamp_int(source.get(
            "label_text_size"), 10, 52, data["label_text_size"])
        data["box_size"] = clamp_int(source.get(
            "box_size"), 6, 18, data["box_size"])
        data["border"] = clamp_int(source.get("border"), 2, 10, data["border"])

    return data


def get_species_admin_filters():
    q = (request.args.get("q") or "").strip()
    familia = (request.args.get("familia") or "").strip()
    orden = (request.args.get("orden") or "").strip()

    query = Species.query
    if q:
        term = f"%{q}%"
        query = query.filter(or_(
            Species.qr_id.ilike(term),
            Species.nombre_comun.ilike(term),
            Species.nombre_cientifico.ilike(term),
            Species.familia.ilike(term),
            Species.orden.ilike(term),
        ))

    if familia:
        query = query.filter(Species.familia == familia)
    if orden:
        query = query.filter(Species.orden == orden)

    items = query.order_by(Species.nombre_comun.asc()).all()

    familias = [
        value for (value,) in db.session.query(Species.familia)
        .filter(Species.familia.isnot(None), Species.familia != "")
        .distinct()
        .order_by(Species.familia.asc())
        .all()
    ]

    ordenes = [
        value for (value,) in db.session.query(Species.orden)
        .filter(Species.orden.isnot(None), Species.orden != "")
        .distinct()
        .order_by(Species.orden.asc())
        .all()
    ]

    return {
        "q": q,
        "familia": familia,
        "orden": orden,
        "items": items,
        "familias": familias,
        "ordenes": ordenes,
    }


def get_species_or_404(species_id: str) -> Species:
    sid = sanitize_id(species_id)
    if not sid or not ID_RE.match(sid):
        abort(404)
    item = db.session.get(Species, sid)
    if not item:
        abort(404)
    return item


def get_module_drawer(style_name: str):
    return {
        "square": SquareModuleDrawer(),
        "rounded": RoundedModuleDrawer(radius_ratio=0.9),
        "circle": CircleModuleDrawer(),
        "gapped": GappedSquareModuleDrawer(size_ratio=0.8),
    }.get(style_name, SquareModuleDrawer())


def fit_text(draw, text, font, max_width: int) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while len(text) > 3 and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def load_qr_font(size: int, *, bold: bool = False):
    target_size = clamp_int(size, 8, 96, 18)
    font_names = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]

    for name in font_names:
        try:
            return ImageFont.truetype(name, target_size)
        except OSError:
            continue

    windows_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    for name in font_names:
        try:
            return ImageFont.truetype(os.path.join(windows_fonts, name), target_size)
        except OSError:
            continue

    try:
        return ImageFont.load_default(size=target_size)
    except TypeError:
        return ImageFont.load_default()


def render_qr_image(species: Species, style_data: dict, qr_value: str | None = None) -> Image.Image:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=style_data["box_size"],
        border=style_data["border"],
    )
    qr_payload = sanitize_id(qr_value if qr_value is not None else (species.qr_id or species.id))
    if not qr_payload:
        qr_payload = species.id
    qr.add_data(qr_payload)
    qr.make(fit=True)

    fill_rgb = ImageColor.getrgb(style_data["fill_color"])
    back_rgb = ImageColor.getrgb(style_data["back_color"])
    accent_rgb = ImageColor.getrgb(style_data["accent_color"])

    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=get_module_drawer(style_data["module_style"]),
        color_mask=SolidFillColorMask(
            front_color=fill_rgb, back_color=back_rgb),
    ).convert("RGBA")

    frame_style = style_data["frame_style"]
    top_text = (style_data.get("top_text") or "").strip()
    label_text = (style_data.get("label_text") or "").strip()
    show_top_text = bool(style_data.get("show_top_text", True)) and bool(top_text)
    show_label_text = bool(style_data.get("show_label_text", True)) and bool(label_text)

    if frame_style == "simple" and not show_top_text and not show_label_text:
        return qr_img

    font_title = load_qr_font(style_data.get("top_text_size", 18), bold=True)
    font_body = load_qr_font(style_data.get("label_text_size", 18), bold=False)
    font_scan = load_qr_font(16, bold=True)

    measure_img = Image.new("RGBA", (8, 8), (255, 255, 255, 0))
    measure_draw = ImageDraw.Draw(measure_img)

    def text_height(text_value: str, font_obj) -> int:
        bbox = measure_draw.textbbox((0, 0), text_value or "Ag", font=font_obj)
        return int(max(1, bbox[3] - bbox[1]))

    top_text_h = text_height(top_text, font_title)
    label_text_h = text_height(label_text, font_body)

    header_h = 0
    if show_top_text:
        header_h = top_text_h + 16
        if frame_style in {"badge", "scanme"}:
            header_h = max(42, header_h)

    footer_h = 18
    if frame_style == "card":
        footer_h = 22
    elif frame_style == "badge":
        footer_h = 20
    elif frame_style == "scanme":
        footer_h = 54

    if show_label_text:
        footer_h += label_text_h + 14

    qr_w, qr_h = qr_img.size
    padding = 26

    canvas_w = qr_w + padding * 2
    canvas_h = qr_h + padding * 2 + header_h + footer_h

    canvas = Image.new("RGBA", (canvas_w, canvas_h), back_rgb +
                       ((255,) if len(back_rgb) == 3 else tuple()))
    draw = ImageDraw.Draw(canvas)

    if frame_style == "card":
        draw.rounded_rectangle((6, 6, canvas_w - 6, canvas_h - 6),
                               radius=32, fill=back_rgb, outline=accent_rgb, width=8)
    elif frame_style == "badge":
        draw.rounded_rectangle((6, 6, canvas_w - 6, canvas_h - 6),
                               radius=34, fill=back_rgb, outline=accent_rgb, width=6)
        if show_top_text:
            draw.rounded_rectangle(
                (18, 18, canvas_w - 18, 18 + header_h), radius=18, fill=accent_rgb)
    elif frame_style == "scanme":
        draw.rounded_rectangle((8, 8, canvas_w - 8, canvas_h - 8),
                               radius=36, fill=back_rgb, outline=accent_rgb, width=8)
        footer_button_h = 34
        draw.rounded_rectangle((24, canvas_h - footer_button_h - 18,
                               canvas_w - 24, canvas_h - 18), radius=16, fill=accent_rgb)
    else:
        draw.rounded_rectangle((10, 10, canvas_w - 10, canvas_h - 10),
                               radius=28, fill=back_rgb, outline=accent_rgb, width=5)

    qr_x = (canvas_w - qr_w) // 2
    qr_y = padding + header_h
    canvas.alpha_composite(qr_img, (qr_x, qr_y))

    if show_top_text:
        header_text = fit_text(draw, top_text, font_title, canvas_w - 60)
        if frame_style == "badge":
            header_y = 18 + header_h // 2
            header_color = back_rgb
        else:
            header_y = padding + header_h // 2
            header_color = fill_rgb
        draw.text((canvas_w // 2, header_y), header_text,
                  anchor="mm", fill=header_color, font=font_title)

    if show_label_text:
        footer_text = fit_text(draw, label_text, font_body, canvas_w - 40)
        label_top = qr_y + qr_h + 10
        label_y = label_top + label_text_h // 2 + 1
        draw.text((canvas_w // 2, label_y), footer_text,
                  anchor="mm", fill=fill_rgb, font=font_body)

    if frame_style == "scanme":
        draw.text((canvas_w // 2, canvas_h - 35), "ESCANEA",
                  anchor="mm", fill=back_rgb, font=font_scan)

    return canvas

# --------- TEXT EXTRACTION ---------


def clamp_percent(raw, default=50):
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(0, min(100, value))


def clamp_zoom(raw, default=100):
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return default
    return max(80, min(200, value))


def ensure_schema_updates():
    rows = db.session.execute(text("PRAGMA table_info(species)")).fetchall()
    cols = {row[1] for row in rows}

    changed = False

    if "qr_id" not in cols:
        db.session.execute(
            text("ALTER TABLE species ADD COLUMN qr_id VARCHAR(64)")
        )
        changed = True

    if "thumb_pos_x" not in cols:
        db.session.execute(
            text("ALTER TABLE species ADD COLUMN thumb_pos_x INTEGER DEFAULT 50")
        )
        changed = True

    if "thumb_pos_y" not in cols:
        db.session.execute(
            text("ALTER TABLE species ADD COLUMN thumb_pos_y INTEGER DEFAULT 50")
        )
        changed = True

    if "thumb_zoom" not in cols:
        db.session.execute(
            text("ALTER TABLE species ADD COLUMN thumb_zoom INTEGER DEFAULT 100")
        )
        changed = True

    species_rows = db.session.execute(
        text("SELECT id, qr_id FROM species ORDER BY id ASC")
    ).fetchall()
    seen_qr_ids = set()

    for sid, qr_id in species_rows:
        base = sanitize_id(qr_id or sid)
        if not base:
            base = "species"

        candidate = base
        suffix = 1
        while candidate in seen_qr_ids:
            candidate = f"{base}-{suffix}"
            suffix += 1

        seen_qr_ids.add(candidate)

        if qr_id != candidate:
            db.session.execute(
                text("UPDATE species SET qr_id = :qr_id WHERE id = :sid"),
                {"qr_id": candidate, "sid": sid},
            )
            changed = True

    idx_rows = db.session.execute(text("PRAGMA index_list(species)")).fetchall()
    has_unique_qr_index = False
    for row in idx_rows:
        idx_name = row[1]
        is_unique = bool(row[2])
        if not is_unique:
            continue

        idx_info = db.session.execute(
            text(f'PRAGMA index_info("{idx_name}")')
        ).fetchall()
        if len(idx_info) == 1 and idx_info[0][2] == "qr_id":
            has_unique_qr_index = True
            break

    if not has_unique_qr_index:
        db.session.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_species_qr_id ON species(qr_id)")
        )
        changed = True

    qr_table = "qr_style"
    qr_rows = db.session.execute(
        text(f'PRAGMA table_info("{qr_table}")')
    ).fetchall()
    qr_cols = {row[1] for row in qr_rows}

    if "show_top_text" not in qr_cols:
        db.session.execute(
            text(f'ALTER TABLE "{qr_table}" ADD COLUMN show_top_text BOOLEAN DEFAULT 1')
        )
        changed = True

    if "show_label_text" not in qr_cols:
        db.session.execute(
            text(f'ALTER TABLE "{qr_table}" ADD COLUMN show_label_text BOOLEAN DEFAULT 1')
        )
        changed = True

    if "top_text_size" not in qr_cols:
        db.session.execute(
            text(f'ALTER TABLE "{qr_table}" ADD COLUMN top_text_size INTEGER DEFAULT 18')
        )
        changed = True

    if "label_text_size" not in qr_cols:
        db.session.execute(
            text(f'ALTER TABLE "{qr_table}" ADD COLUMN label_text_size INTEGER DEFAULT 18')
        )
        changed = True

    null_rows = db.session.execute(
        text(
            f'SELECT COUNT(*) FROM "{qr_table}" '
            "WHERE show_top_text IS NULL OR show_label_text IS NULL "
            "OR top_text_size IS NULL OR label_text_size IS NULL"
        )
    ).scalar() or 0
    if int(null_rows) > 0:
        db.session.execute(
            text(
                f'UPDATE "{qr_table}" SET '
                "show_top_text = COALESCE(show_top_text, 1), "
                "show_label_text = COALESCE(show_label_text, 1), "
                "top_text_size = COALESCE(top_text_size, 18), "
                "label_text_size = COALESCE(label_text_size, 18)"
            )
        )
        changed = True

    if changed:
        db.session.commit()


def extract_text_from_pdf(filepath: str) -> str:
    try:
        reader = PdfReader(filepath)
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception:
        return ""


def extract_text_from_docx(filepath: str) -> str:
    try:
        d = docx.Document(filepath)
        return "\n".join(p.text for p in d.paragraphs).strip()
    except Exception:
        return ""


def extract_text_from_txt(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


# --------- APP ---------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///bioscan.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

llm = LLMClient()
with app.app_context():
    db.create_all()
    ensure_schema_updates()
# Lazy init VectorStore (evita ruido en CLI)
_VS = None


def get_vs():
    global _VS
    if _VS is None:
        from vector_store import VectorStore
        _VS = VectorStore()
    return _VS


def get_chat_history(user_id: int, species_id: str, limit: int = 8):
    turns = (ChatTurn.query
             .filter_by(user_id=user_id, species_id=species_id)
             .order_by(ChatTurn.created_at.desc())
             .limit(limit)
             .all())
    turns = list(reversed(turns))
    return [{"role": t.role, "content": t.content} for t in turns]


def save_chat_turns(user_id: int, species_id: str, user_text: str, assistant_text: str, keep_last: int = 60):
    db.session.add(ChatTurn(user_id=user_id, species_id=species_id,
                   role="user", content=user_text))
    db.session.add(ChatTurn(user_id=user_id, species_id=species_id,
                   role="assistant", content=assistant_text))
    db.session.commit()

    old = (ChatTurn.query
           .filter_by(user_id=user_id, species_id=species_id)
           .order_by(ChatTurn.created_at.desc())
           .offset(keep_last)
           .all())
    for t in old:
        db.session.delete(t)
    if old:
        db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/logout", endpoint="logout")
@login_required
def logout_view():
    logout_user()
    return redirect(url_for("index"))


@app.post("/api/chat_stream")
def api_chat_stream():
    import requests
    import urllib.parse

    # 1) exigir login (para memoria individual)
    if not current_user.is_authenticated:
        return Response("LOGIN_REQUIRED", status=401, mimetype="text/plain")

    def wiki_search_title(query: str) -> str:
        if not query:
            return ""
        q = urllib.parse.quote(query)
        url = (
            "https://es.wikipedia.org/w/api.php"
            f"?action=query&format=json&list=search&srsearch={q}&srlimit=1"
        )
        try:
            r = requests.get(url, timeout=8)
            if r.status_code != 200:
                return ""
            data = r.json()
            results = data.get("query", {}).get("search", [])
            return (results[0].get("title") or "").strip() if results else ""
        except Exception:
            return ""

    def wiki_extract(title: str, max_chars: int = 2500) -> str:
        if not title:
            return ""
        t = urllib.parse.quote(title)
        url = (
            "https://es.wikipedia.org/w/api.php"
            f"?action=query&format=json&prop=extracts&explaintext=1&redirects=1&titles={t}"
        )
        try:
            r = requests.get(url, timeout=8)
            if r.status_code != 200:
                return ""
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            if not pages:
                return ""
            page = next(iter(pages.values()))
            text = (page.get("extract") or "").strip()
            return text[:max_chars].strip() if text else ""
        except Exception:
            return ""

    def last_pair(history: list[dict]) -> tuple[str, str]:
        """
        Devuelve (ultima_pregunta_usuario, ultima_respuesta_asistente) del historial.
        Si no hay, retorna ("","").
        """
        if not history:
            return "", ""
        # buscamos desde el final: assistant y el user previo
        last_assistant = ""
        last_user = ""
        for i in range(len(history) - 1, -1, -1):
            if history[i]["role"] == "assistant" and not last_assistant:
                last_assistant = history[i]["content"]
                # seguimos buscando user anterior
                continue
            if last_assistant and history[i]["role"] == "user":
                last_user = history[i]["content"]
                break
        return last_user, last_assistant

    data = request.get_json(silent=True) or {}
    species_id = sanitize_id(data.get("species_id") or "")
    user_msg = (data.get("message") or "").strip()

    if not species_id or not ID_RE.match(species_id):
        return Response("ERROR: species_id inválido", status=400, mimetype="text/plain")
    if not user_msg:
        return Response("ERROR: mensaje vacío", status=400, mimetype="text/plain")

    sp = db.session.get(Species, species_id)
    if not sp:
        return Response("ERROR: Especie no encontrada", status=404, mimetype="text/plain")

    # -------- Memoria (historial): tomamos SOLO el último par --------
    hist = get_chat_history(current_user.id, species_id, limit=10)
    prev_q, prev_a = last_pair(hist)

    memory_note = ""
    if prev_q and prev_a:
        memory_note = (
            "Contexto de conversación previa (para referencias como '¿por qué?' / '¿cómo así?'):\n"
            f"- Pregunta anterior del usuario: {prev_q}\n"
            f"- Tu respuesta anterior: {prev_a}\n\n"
            "Regla: NO repitas la respuesta anterior completa. "
            "Responde SOLO a la pregunta NUEVA del usuario, usando la respuesta anterior solo como referencia breve."
        )

    # -------- Recorrido (últimas escaneadas) --------
    tour_note = ""
    last = (db.session.query(Visit, Species)
            .join(Species, Species.id == Visit.species_id)
            .filter(Visit.user_id == current_user.id)
            .order_by(Visit.visited_at.desc())
            .limit(8)
            .all())

    if last:
        lines = []
        current_family = (sp.familia or "").strip().lower()
        same_family = []
        for v, s in last:
            fam = s.familia or "?"
            lines.append(f"- {s.nombre_comun} ({s.id}) — familia: {fam}")
            if current_family and s.id != sp.id and (s.familia or "").strip().lower() == current_family:
                same_family.append(f"{s.nombre_comun} ({s.id})")

        tour_note = "Recorrido reciente del usuario:\n" + "\n".join(lines)
        if same_family:
            tour_note += "\n\nRelación:\n" + \
                f"Esta especie comparte familia ({sp.familia}) con: " + \
                ", ".join(same_family) + "."

    structured = build_structured_context(current_user.id, sp)

    # -------- 1) RAG --------
    try:
        chunks = get_vs().query_species(species_id, user_msg, k=4)
    except Exception:
        chunks = []

    rag_context = ""
    if chunks:
        rag_context = "Fragmentos del museo (RAG):\n" + \
            "\n\n".join([f"- {c['text']}" for c in chunks])
    else:
        rag_context = "Fragmentos del museo (RAG): No hay información del museo indexada o relevante."

    # -------- 2) Web fallback SOLO si NO hay chunks --------
    wiki_text = ""
    wiki_url = ""
    if len(chunks) == 0:
        candidates = []
        if (sp.nombre_cientifico or "").strip():
            candidates.append(sp.nombre_cientifico.strip())
        if (sp.nombre_comun or "").strip():
            candidates.append(sp.nombre_comun.strip())
            candidates.append(sp.nombre_comun.strip() + " andino")

        title = ""
        for cand in candidates:
            title = wiki_search_title(cand)
            if title:
                break

        if title:
            wiki_text = wiki_extract(title)
            wiki_url = "https://es.wikipedia.org/wiki/" + \
                urllib.parse.quote(title.replace(" ", "_"))

    # -------- System prompt (clave para evitar duplicar) --------
    system = (
        "Eres un guía del museo. Responde en español, claro y amable.\n"
        "Responde SOLO a la ÚLTIMA pregunta del usuario.\n"
        "Si es una pregunta de seguimiento (por qué / cómo / entonces / como cuáles), "
        "NO repitas la respuesta anterior completa: responde directo al punto.\n"
        "NO hagas preguntas ni sugieras preguntas.\n"
        "Si el usuario pide ejemplos ('¿como cuáles?'), da 3–5 ejemplos concretos.\n"
        "Si usas Wikipedia, añade al final EXACTAMENTE:\n"
        "Fuente externa: Wikipedia (puede contener errores) — <URL>\n"
        "No inventes datos."
    )

    full_context = (
        "Ficha (BD):\n" + structured + "\n\n" +
        (memory_note + "\n\n" if memory_note else "") +
        (tour_note + "\n\n" if tour_note else "") +
        rag_context +
        (("\n\nTexto Wikipedia:\n" + wiki_text +
         "\n\nURL: " + wiki_url) if wiki_text else "")
    )

    # ✅ IMPORTANTÍSIMO: NO metemos todo el historial crudo (eso causaba la repetición)
    messages = [
        {"role": "system", "content": system},
        {"role": "system", "content": full_context},
        {"role": "user", "content": user_msg},
    ]

    def generate():
        full_answer = ""
        try:
            for chunk in llm.stream(messages):
                full_answer += chunk
                yield chunk

            # si usó wiki y el modelo olvidó la línea final, la pegamos
            if wiki_text and wiki_url and ("Fuente externa: Wikipedia" not in full_answer):
                full_answer = full_answer.rstrip(
                ) + f"\n\nFuente externa: Wikipedia (puede contener errores) — {wiki_url}"

            save_chat_turns(current_user.id, species_id,
                            user_msg, full_answer.strip(), keep_last=60)

        except Exception as e:
            yield f"\n\n[ERROR] {e}"

    return Response(stream_with_context(generate()), mimetype="text/plain; charset=utf-8")
# --------- ROUTES ---------


@app.get("/")
def index():
    return render_template("index.html")

# ----- AUTH -----


@app.get("/login")
def login():
    return render_template("login.html")


@app.post("/login")
def login_post():
    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        flash("Usuario o contraseña incorrectos", "error")
        return redirect(url_for("login"))

    login_user(user)

    next_url = request.args.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect(url_for("index"))
# --------------------------------------


@app.get("/register")
def register():
    return render_template("register.html")


@app.post("/register")
def register_post():
    nombre = (request.form.get("nombre") or "").strip()
    edad_raw = (request.form.get("edad") or "").strip()
    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    # Validaciones
    if not nombre:
        flash("El nombre es obligatorio.", "error")
        return redirect(url_for("register"))

    try:
        edad = int(edad_raw)
        if edad < 1 or edad > 120:
            raise ValueError()
    except Exception:
        flash("La edad debe ser un número válido (1-120).", "error")
        return redirect(url_for("register"))

    if not username or len(username) < 3:
        flash("El nombre de usuario debe tener al menos 3 caracteres.", "error")
        return redirect(url_for("register"))

    if password != password2:
        flash("Las contraseñas no coinciden.", "error")
        return redirect(url_for("register"))

    if len(password) < 6:
        flash("La contraseña debe tener al menos 6 caracteres.", "error")
        return redirect(url_for("register"))

    if User.query.filter_by(username=username).first():
        flash("Ese nombre de usuario ya existe. Elige otro.", "error")
        return redirect(url_for("register"))

    # Crear usuario
    u = User(nombre=nombre, edad=edad, username=username, is_admin=False)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()

    login_user(u)
    flash("Cuenta creada correctamente ✅", "ok")
    return redirect(url_for("index"))
# --------------------------------------historial--------------


def get_chat_history(user_id: int, species_id: str, limit: int = 8):
    # últimos turnos (user+assistant), ordenados del más viejo al más nuevo
    turns = (ChatTurn.query
             .filter_by(user_id=user_id, species_id=species_id)
             .order_by(ChatTurn.created_at.desc())
             .limit(limit)
             .all())
    turns = list(reversed(turns))
    return [{"role": t.role, "content": t.content} for t in turns]


def save_turn(user_id: int, species_id: str, role: str, content: str):
    db.session.add(
        ChatTurn(user_id=user_id, species_id=species_id, role=role, content=content))
    db.session.commit()
# ----- LIST -----


@app.get("/especies")
def especies():
    q = (request.args.get("q") or "").strip().lower()
    query = Species.query
    if q:
        query = query.filter(
            (Species.qr_id.ilike(f"%{q}%")) |
            (Species.nombre_comun.ilike(f"%{q}%")) |
            (Species.nombre_cientifico.ilike(f"%{q}%"))
        )

    items = query.order_by(Species.nombre_comun.asc()).all()

    total_count = Species.query.count()

    scanned_ids = set()
    scanned_count = 0
    if current_user.is_authenticated:
        rows = (db.session.query(Visit.species_id)
                .filter(Visit.user_id == current_user.id)
                .distinct()
                .all())
        scanned_ids = set([r[0] for r in rows])
        scanned_count = len(scanned_ids)

    # escaneos totales por especie (usuarios distintos)
    counts = (db.session.query(Visit.species_id, db.func.count(db.func.distinct(Visit.user_id)))
              .group_by(Visit.species_id)
              .all())
    scan_counts = {sid: c for sid, c in counts}

    return render_template(
        "especies.html",
        items=items, q=q,
        total_count=total_count,
        scanned_count=scanned_count,
        scanned_ids=scanned_ids,
        scan_counts=scan_counts
    )
# -------------------------


@app.get("/scan/<qr_id>")
@login_required
def scan_species(qr_id):
    normalized_qr_id = sanitize_id(qr_id)
    if not normalized_qr_id or not ID_RE.match(normalized_qr_id):
        abort(404)

    item = Species.query.filter_by(qr_id=normalized_qr_id).first()
    if not item:
        abort(404)

    # Guardar “escaneada” UNA sola vez por usuario
    exists = Visit.query.filter_by(
        user_id=current_user.id, species_id=item.id).first()
    if not exists:
        db.session.add(Visit(user_id=current_user.id, species_id=item.id))
        db.session.commit()

    return redirect(url_for("especie", qr_id=item.qr_id))
# ----- DETAIL -----


@app.get("/especie/<qr_id>")
def especie(qr_id):
    normalized_qr_id = sanitize_id(qr_id)
    if not normalized_qr_id or not ID_RE.match(normalized_qr_id):
        abort(404)

    item = Species.query.filter_by(qr_id=normalized_qr_id).first()
    if not item:
        abort(404)

    is_scanned = False
    if current_user.is_authenticated:
        is_scanned = Visit.query.filter_by(
            user_id=current_user.id, species_id=item.id).first() is not None

    return render_template("especie.html", item=item, is_scanned=is_scanned)

# --------- ADMIN CRUD ---------


@app.get("/admin/especies")
@login_required
def admin_species_list():
    admin_required()
    return render_template("admin_species_list.html", **get_species_admin_filters())


@app.get("/admin/especies/nueva")
@login_required
def admin_species_new():
    admin_required()
    return render_template("admin_species_form.html", item=None, docs=[])


def handle_uploads_for_species(species_id: str, species_obj: Species):
    ensure_dir(UPLOAD_DIR)
    species_folder = os.path.join(UPLOAD_DIR, species_id)
    ensure_dir(species_folder)

    # 1) Imagen
    image_file = request.files.get("imagen_file")
    if image_file and image_file.filename:
        if not allowed(image_file.filename, ALLOWED_IMAGES):
            raise ValueError("Imagen inválida. Solo .jpg, .jpeg, .png o .webp")
        stored_name = unique_name("img", image_file.filename)
        abs_path = os.path.join(species_folder, stored_name)
        image_file.save(abs_path)
        species_obj.imagen = f"uploads/{species_id}/{stored_name}"

    # 2) Audio MP3
    audio_file = request.files.get("audio_file")
    if audio_file and audio_file.filename:
        if not allowed(audio_file.filename, ALLOWED_AUDIO):
            raise ValueError("Audio inválido. Solo .mp3")
        stored_name = unique_name("audio", audio_file.filename)
        abs_path = os.path.join(species_folder, stored_name)
        audio_file.save(abs_path)
        species_obj.audio = f"uploads/{species_id}/{stored_name}"

    # 3) Docs museo (múltiples)
    doc_files = request.files.getlist("museo_docs")
    for f in doc_files:
        if not f or not f.filename:
            continue
        if not allowed(f.filename, ALLOWED_DOCS):
            raise ValueError("Documento inválido. Solo .pdf, .docx o .txt")

        stored_name = unique_name("doc", f.filename)
        abs_path = os.path.join(species_folder, stored_name)
        f.save(abs_path)

        fext = ext_of(f.filename)
        if fext == "pdf":
            extracted = extract_text_from_pdf(abs_path)
        elif fext == "docx":
            extracted = extract_text_from_docx(abs_path)
        else:
            extracted = extract_text_from_txt(abs_path)

        doc_row = MuseumDoc(
            species_id=species_id,
            stored_path=f"uploads/{species_id}/{stored_name}",
            original_name=secure_filename(f.filename),
            file_type=fext,
            extracted_text=extracted
        )
        db.session.add(doc_row)


@app.post("/admin/especies/nueva")
@login_required
def admin_species_new_post():
    admin_required()

    qr_id = sanitize_id(request.form.get("qr_id"))
    if not qr_id or not ID_RE.match(qr_id):
        flash("ID QR inválido. Usa solo letras/números/guion/guion_bajo (ej: condor-001).", "error")
        return redirect(url_for("admin_species_new"))
    if Species.query.filter_by(qr_id=qr_id).first():
        flash("Ese ID QR ya existe.", "error")
        return redirect(url_for("admin_species_new"))

    sid = qr_id
    if db.session.get(Species, sid):
        flash("No se pudo crear la especie. Intenta con otro ID QR.", "error")
        return redirect(url_for("admin_species_new"))

    nombre_comun = (request.form.get("nombre_comun") or "").strip()
    if not nombre_comun:
        flash("Nombre común es obligatorio.", "error")
        return redirect(url_for("admin_species_new"))

    sp = Species(
        id=sid,
        qr_id=qr_id,
        nombre_comun=nombre_comun,
        nombre_cientifico=(request.form.get(
            "nombre_cientifico") or "").strip(),
        familia=(request.form.get("familia") or "").strip(),
        orden=(request.form.get("orden") or "").strip(),
        descripcion=(request.form.get("descripcion") or "").strip(),
        habitat=(request.form.get("habitat") or "").strip(),
        dieta=(request.form.get("dieta") or "").strip(),
        zonas=(request.form.get("zonas") or "").strip(),
        map_embed_url=(request.form.get("map_embed_url") or "").strip(),
        museo_info=(request.form.get("museo_info") or "").strip(),
        thumb_pos_x=clamp_percent(request.form.get("thumb_pos_x"), 50),
        thumb_pos_y=clamp_percent(request.form.get("thumb_pos_y"), 50),
        thumb_zoom=clamp_zoom(request.form.get("thumb_zoom"), 100),
    )

    curiosidades_raw = (request.form.get("curiosidades") or "").strip()
    sp.curiosidades = [x.strip()
                       for x in curiosidades_raw.split("\n") if x.strip()]

    db.session.add(sp)

    try:
        handle_uploads_for_species(sp.id, sp)
    except ValueError as ve:
        db.session.rollback()
        flash(str(ve), "error")
        return redirect(url_for("admin_species_new"))

    db.session.commit()

    try:
        get_vs().reindex_species(sp.id, sp.museo_info)
    except Exception as e:
        flash(f"Guardado OK, pero falló indexación RAG: {e}", "error")

    return redirect(url_for("admin_species_list"))


@app.get("/admin/especies/<species_id>/editar")
@login_required
def admin_species_edit(species_id):
    admin_required()
    sid = sanitize_id(species_id)
    item = db.session.get(Species, sid)
    if not item:
        abort(404)
    docs = MuseumDoc.query.filter_by(species_id=item.id).order_by(
        MuseumDoc.created_at.desc()).all()
    return render_template("admin_species_form.html", item=item, docs=docs)


@app.post("/admin/especies/<species_id>/editar")
@login_required
def admin_species_edit_post(species_id):
    admin_required()
    sid = sanitize_id(species_id)
    item = db.session.get(Species, sid)
    if not item:
        abort(404)

    nombre_comun = (request.form.get("nombre_comun") or "").strip()
    if not nombre_comun:
        flash("Nombre común es obligatorio.", "error")
        return redirect(url_for("admin_species_edit", species_id=item.id))

    item.nombre_comun = nombre_comun
    item.nombre_cientifico = (request.form.get(
        "nombre_cientifico") or "").strip()
    item.familia = (request.form.get("familia") or "").strip()
    item.orden = (request.form.get("orden") or "").strip()
    item.descripcion = (request.form.get("descripcion") or "").strip()
    item.habitat = (request.form.get("habitat") or "").strip()
    item.dieta = (request.form.get("dieta") or "").strip()
    item.zonas = (request.form.get("zonas") or "").strip()
    item.map_embed_url = (request.form.get("map_embed_url") or "").strip()
    item.museo_info = (request.form.get("museo_info") or "").strip()

    item.thumb_pos_x = clamp_percent(request.form.get("thumb_pos_x"), 50)
    item.thumb_pos_y = clamp_percent(request.form.get("thumb_pos_y"), 50)
    item.thumb_zoom = clamp_zoom(request.form.get("thumb_zoom"), 100)

    curiosidades_raw = (request.form.get("curiosidades") or "").strip()
    item.curiosidades = [x.strip()
                         for x in curiosidades_raw.split("\n") if x.strip()]

    try:
        handle_uploads_for_species(item.id, item)
    except ValueError as ve:
        db.session.rollback()
        flash(str(ve), "error")
        return redirect(url_for("admin_species_edit", species_id=item.id))

    db.session.commit()

    try:
        get_vs().reindex_species(item.id, item.museo_info)
    except Exception as e:
        flash(f"Editado OK, pero falló indexación RAG: {e}", "error")

    return redirect(url_for("admin_species_list"))


@app.post("/admin/especies/<species_id>/eliminar")
@login_required
def admin_species_delete(species_id):
    admin_required()
    sid = sanitize_id(species_id)
    item = db.session.get(Species, sid)
    if not item:
        abort(404)

    MuseumDoc.query.filter_by(species_id=item.id).delete()
    db.session.delete(item)
    db.session.commit()

    try:
        get_vs().reindex_species(sid, "")
    except Exception:
        pass

    return redirect(url_for("admin_species_list"))


@app.post("/admin/especies/<species_id>/docs/<int:doc_id>/eliminar")
@login_required
def admin_doc_delete(species_id, doc_id):
    admin_required()
    sid = sanitize_id(species_id)
    doc = db.session.get(MuseumDoc, doc_id)
    if not doc or doc.species_id != sid:
        abort(404)

    abs_file = os.path.join("static", doc.stored_path.replace("\\", "/"))
    try:
        if os.path.exists(abs_file):
            os.remove(abs_file)
    except Exception:
        pass

    db.session.delete(doc)
    db.session.commit()

    sp = db.session.get(Species, sid)
    if sp:
        try:
            get_vs().reindex_species(sid, sp.museo_info)
        except Exception as e:
            flash(f"Doc eliminado, pero falló reindex: {e}", "error")

    return redirect(url_for("admin_species_edit", species_id=sid))


@app.post("/admin/especies/<species_id>/reindex")
@login_required
def admin_reindex(species_id):
    admin_required()
    sid = sanitize_id(species_id)
    sp = db.session.get(Species, sid)
    if not sp:
        abort(404)
    try:
        get_vs().reindex_species(sid, sp.museo_info)
        flash("Reindexación RAG completada.", "ok")
    except Exception as e:
        flash(f"Falló reindex: {e}", "error")
    return redirect(url_for("admin_species_edit", species_id=sid))


@app.get("/admin/qr")
@login_required
def admin_qr_list():
    admin_required()
    ctx = get_species_admin_filters()
    styled_ids = {sid for (sid,) in db.session.query(QRStyle.species_id).all()}
    return render_template("admin_qr_list.html", styled_ids=styled_ids, **ctx)


@app.get("/admin/qr/<species_id>")
@login_required
def admin_qr_view(species_id):
    admin_required()
    item = get_species_or_404(species_id)
    style_obj = db.session.get(QRStyle, item.id)
    qr_style = get_qr_style_dict(item, style_obj)
    has_custom_style = style_obj is not None
    return render_template(
        "admin_qr_view.html",
        item=item,
        qr_style=qr_style,
        has_custom_style=has_custom_style,
    )


@app.get("/admin/qr/<species_id>/personalizar")
@login_required
def admin_qr_customize(species_id):
    admin_required()
    item = get_species_or_404(species_id)
    style_obj = db.session.get(QRStyle, item.id)
    qr_style = get_qr_style_dict(item, style_obj)
    return render_template(
        "admin_qr_customize.html",
        item=item,
        qr_style=qr_style,
        frame_options=QR_FRAME_OPTIONS,
        module_options=QR_MODULE_OPTIONS,
        has_custom_style=style_obj is not None,
    )


@app.post("/admin/qr/<species_id>/personalizar")
@login_required
def admin_qr_customize_post(species_id):
    admin_required()
    item = get_species_or_404(species_id)
    style_obj = db.session.get(QRStyle, item.id)
    if style_obj is None:
        style_obj = QRStyle(species_id=item.id)
        db.session.add(style_obj)

    new_qr_id = sanitize_id(request.form.get("qr_id"))
    if not new_qr_id or not ID_RE.match(new_qr_id):
        flash("ID QR inválido. Usa solo letras/números/guion/guion_bajo.", "error")
        return redirect(url_for("admin_qr_customize", species_id=item.id))

    conflict = (Species.query
                .filter(Species.qr_id == new_qr_id, Species.id != item.id)
                .first())
    if conflict:
        flash("Ese ID QR ya está en uso por otra especie.", "error")
        return redirect(url_for("admin_qr_customize", species_id=item.id))

    item.qr_id = new_qr_id

    data = get_qr_style_dict(item, style_obj, request.form)
    style_obj.frame_style = data["frame_style"]
    style_obj.module_style = data["module_style"]
    style_obj.fill_color = data["fill_color"]
    style_obj.back_color = data["back_color"]
    style_obj.accent_color = data["accent_color"]
    style_obj.label_text = data["label_text"]
    style_obj.top_text = data["top_text"]
    style_obj.show_top_text = data["show_top_text"]
    style_obj.show_label_text = data["show_label_text"]
    style_obj.top_text_size = data["top_text_size"]
    style_obj.label_text_size = data["label_text_size"]
    style_obj.box_size = data["box_size"]
    style_obj.border = data["border"]

    db.session.commit()
    flash("QR personalizado guardado.", "ok")
    return redirect(url_for("admin_qr_customize", species_id=item.id))


@app.post("/admin/qr/<species_id>/personalizar/reset")
@login_required
def admin_qr_reset(species_id):
    admin_required()
    item = get_species_or_404(species_id)
    style_obj = db.session.get(QRStyle, item.id)
    if style_obj:
        db.session.delete(style_obj)
        db.session.commit()
    flash("QR restablecido al estilo simple.", "ok")
    return redirect(url_for("admin_qr_customize", species_id=item.id))


@app.get("/admin/qr/<species_id>/imagen.<fmt>")
@login_required
def admin_qr_image(species_id, fmt):
    admin_required()
    item = get_species_or_404(species_id)
    style_obj = db.session.get(QRStyle, item.id)
    style_data = get_qr_style_dict(
        item, style_obj, request.args if request.args else None)
    preview_qr_id = sanitize_id(request.args.get("preview_qr_id"))
    qr_value = item.qr_id or item.id
    if preview_qr_id and ID_RE.match(preview_qr_id):
        qr_value = preview_qr_id

    img = render_qr_image(item, style_data, qr_value=qr_value)

    fmt = (fmt or "png").lower()
    if fmt not in {"png", "jpg", "jpeg"}:
        abort(404)

    download = request.args.get("download") == "1"
    filename = f"qr-{qr_value}.{'jpg' if fmt in {'jpg', 'jpeg'} else 'png'}"

    bio = BytesIO()
    if fmt in {"jpg", "jpeg"}:
        if img.mode != "RGB":
            background = Image.new(
                "RGB", img.size, ImageColor.getrgb(style_data["back_color"]))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        img.save(bio, format="JPEG", quality=95)
        mimetype = "image/jpeg"
    else:
        img.save(bio, format="PNG")
        mimetype = "image/png"

    headers = {}
    disposition = "attachment" if download else "inline"
    headers["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return Response(bio.getvalue(), mimetype=mimetype, headers=headers)

# --------- CHAT API (RAG) ---------


@app.get("/api/public/species/<string:qr_id>/tts")
def get_species_for_tts(qr_id):
    expected_api_key = (os.getenv("MUSEO_TTS_SHARED_KEY") or "").strip()
    provided_api_key = (request.headers.get("X-API-Key") or "").strip()
    if not expected_api_key or provided_api_key != expected_api_key:
        return jsonify({"error": "unauthorized"}), 401

    normalized_qr_id = sanitize_id(qr_id)
    if not normalized_qr_id or not ID_RE.match(normalized_qr_id):
        return jsonify({"error": "species_not_found"}), 404

    item = Species.query.filter_by(qr_id=normalized_qr_id).first()
    if not item:
        return jsonify({"error": "species_not_found"}), 404

    return jsonify({
        "common_name": item.nombre_comun,
        "scientific_name": item.nombre_cientifico,
        "description": item.descripcion,
        "habitat": item.habitat,
        "diet": item.dieta,
        "curiosities": item.curiosidades,
    }), 200


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    species_id = sanitize_id(data.get("species_id") or "")
    user_msg = (data.get("message") or "").strip()

    if not species_id or not ID_RE.match(species_id):
        return jsonify({"ok": False, "error": "species_id inválido"}), 400
    if not user_msg:
        return jsonify({"ok": False, "error": "mensaje vacío"}), 400

    sp = db.session.get(Species, species_id)
    if not sp:
        return jsonify({"ok": False, "error": "Especie no encontrada"}), 404

    user_id = current_user.id if current_user.is_authenticated else None
    structured = build_structured_context(user_id, sp)

    try:
        chunks = get_vs().query_species(species_id, user_msg, k=4)
    except Exception as e:
        chunks = []
    if chunks:
        museum_context = "FRAGMENTOS RELEVANTES DEL MUSEO (RAG):\n" + "\n\n".join([
            f"- {c['text']}" for c in chunks])
    else:
        museum_context = "FRAGMENTOS RELEVANTES DEL MUSEO (RAG): No hay info indexada o no se pudo extraer."

    system = (
        "Eres un guía del museo. Responde en español, claro y amable. "
        "Usa SOLO el contexto proporcionado. "
        "Si no es posible responder con el contexto, dilo y sugiere qué dato faltaría."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "system", "content": structured},
        {"role": "system", "content": museum_context},
        {"role": "user", "content": user_msg},
    ]

    try:
        answer = llm.chat(messages)
        return jsonify({"ok": True, "answer": answer})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# --------- ERRORS ---------


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html", msg="No encontrado"), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("404.html", msg="Acceso denegado"), 403

# --------- CLI ---------


@app.cli.command("init-db")
def init_db():
    with app.app_context():
        db.create_all()
        ensure_schema_updates()
    print("✅ DB inicializada")


@app.cli.command("create-admin")
def create_admin():
    username = os.getenv("ADMIN_USER", "admin").strip().lower()
    password = os.getenv("ADMIN_PASS", "admin123")

    with app.app_context():
        db.create_all()
        ensure_schema_updates()
        if User.query.filter_by(username=username).first():
            print("⚠️ Admin ya existe")
            return
        u = User(nombre="Administrador", edad=99,
                 username=username, is_admin=True)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()

    print(f"✅ Admin creado: {username} / {password}")


@app.cli.command("create-user")
def create_user():
    username = os.getenv("USER_NAME", "user").strip().lower()
    password = os.getenv("USER_PASS", "user123")
    nombre = os.getenv("USER_FULLNAME", "Usuario")
    edad = int(os.getenv("USER_AGE", "20"))

    with app.app_context():
        db.create_all()
        ensure_schema_updates()
        if User.query.filter_by(username=username).first():
            print("⚠️ Usuario ya existe")
            return
        u = User(nombre=nombre, edad=edad, username=username, is_admin=False)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()

    print(f"✅ Usuario creado: {username} / {password}")


@app.cli.command("seed")
def seed():
    with app.app_context():
        db.create_all()
        ensure_schema_updates()
        if db.session.get(Species, "condor-001"):
            print("⚠️ Seed ya aplicado")
            return
        sp = Species(
            id="condor-001",
            qr_id="condor-001",
            nombre_comun="Cóndor Andino",
            nombre_cientifico="Vultur gryphus",
            descripcion="Ave carroñera emblemática de los Andes.",
            habitat="Zonas montañosas andinas.",
            dieta="Carroña.",
            zonas="Andes (Colombia, Ecuador, Perú, Bolivia, Chile, Argentina).",
            map_embed_url="",
            museo_info="Dato del museo: símbolo cultural en varias regiones andinas."
        )
        sp.curiosidades = ["Planea largas distancias",
                           "Aprovecha corrientes térmicas"]
        db.session.add(sp)
        db.session.commit()
        try:
            get_vs().reindex_species(sp.id, sp.museo_info)
        except Exception:
            pass
    print("✅ Seed aplicado")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
