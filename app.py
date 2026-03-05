import os
import re
import uuid
from flask import Flask, render_template, redirect, url_for, request, abort, jsonify, flash,Response, stream_with_context
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from PyPDF2 import PdfReader
import docx

from models import db, User, Species, MuseumDoc, Visit
from llm import LLMClient
from rag import build_structured_context

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

def allowed(filename: str, allowed_set: set[str]) -> bool:
    return ext_of(filename) in allowed_set

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def unique_name(prefix: str, filename: str) -> str:
    safe = secure_filename(filename)
    return f"{prefix}_{uuid.uuid4().hex}_{safe}"

# --------- TEXT EXTRACTION ---------
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
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///bioscan.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

llm = LLMClient()

# Lazy init VectorStore (evita ruido en CLI)
_VS = None
def get_vs():
    global _VS
    if _VS is None:
        from vector_store import VectorStore
        _VS = VectorStore()
    return _VS

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)

@app.get("/favicon.ico")
def favicon():
    return "", 204
@app.post("/api/chat_stream")
def api_chat_stream():
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

    user_id = current_user.id if current_user.is_authenticated else None
    structured = build_structured_context(user_id, sp)

    try:
        chunks = get_vs().query_species(species_id, user_msg, k=4)
    except Exception:
        chunks = []

    if chunks:
        museum_context = "FRAGMENTOS RELEVANTES DEL MUSEO (RAG):\n" + "\n\n".join([f"- {c['text']}" for c in chunks])
    else:
        museum_context = "FRAGMENTOS RELEVANTES DEL MUSEO (RAG): No hay info indexada o no se pudo extraer."

    system = (
        "Eres un guía del museo. Responde en español, claro y amable. "
        "Usa SOLO el contexto proporcionado. "
        "Si no es posible responder con el contexto, dilo."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "system", "content": structured},
        {"role": "system", "content": museum_context},
        {"role": "user", "content": user_msg},
    ]

    def generate():
        try:
            for chunk in llm.stream(messages):
                yield chunk
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
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        flash("Usuario o contraseña incorrectos", "error")
        return redirect(url_for("login"))
    login_user(user)
    return redirect(url_for("index"))

@app.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

# ----- LIST -----
@app.get("/especies")
def especies():
    q = (request.args.get("q") or "").strip().lower()
    query = Species.query
    if q:
        query = query.filter(
            (Species.id.ilike(f"%{q}%")) |
            (Species.nombre_comun.ilike(f"%{q}%")) |
            (Species.nombre_cientifico.ilike(f"%{q}%"))
        )
    items = query.order_by(Species.nombre_comun.asc()).all()
    return render_template("especies.html", items=items, q=q)

# ----- DETAIL -----
@app.get("/especie/<species_id>")
def especie(species_id):
    sid = sanitize_id(species_id)
    if not sid or not ID_RE.match(sid):
        abort(404)

    item = db.session.get(Species, sid)
    if not item:
        abort(404)

    if current_user.is_authenticated:
        db.session.add(Visit(user_id=current_user.id, species_id=item.id))
        db.session.commit()

    return render_template("especie.html", item=item)

# --------- ADMIN CRUD ---------
@app.get("/admin/especies")
@login_required
def admin_species_list():
    admin_required()
    items = Species.query.order_by(Species.nombre_comun.asc()).all()
    return render_template("admin_species_list.html", items=items)

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

    sid = sanitize_id(request.form.get("id"))
    if not sid or not ID_RE.match(sid):
        flash("ID inválido. Usa solo letras/números/guion/guion_bajo (ej: condor-001).", "error")
        return redirect(url_for("admin_species_new"))
    if db.session.get(Species, sid):
        flash("Ese ID ya existe.", "error")
        return redirect(url_for("admin_species_new"))

    nombre_comun = (request.form.get("nombre_comun") or "").strip()
    if not nombre_comun:
        flash("Nombre común es obligatorio.", "error")
        return redirect(url_for("admin_species_new"))

    sp = Species(
        id=sid,
        nombre_comun=nombre_comun,
        nombre_cientifico=(request.form.get("nombre_cientifico") or "").strip(),
        descripcion=(request.form.get("descripcion") or "").strip(),
        habitat=(request.form.get("habitat") or "").strip(),
        dieta=(request.form.get("dieta") or "").strip(),
        zonas=(request.form.get("zonas") or "").strip(),
        map_embed_url=(request.form.get("map_embed_url") or "").strip(),
        museo_info=(request.form.get("museo_info") or "").strip(),
    )
    curiosidades_raw = (request.form.get("curiosidades") or "").strip()
    sp.curiosidades = [x.strip() for x in curiosidades_raw.split("\n") if x.strip()]

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
    docs = MuseumDoc.query.filter_by(species_id=item.id).order_by(MuseumDoc.created_at.desc()).all()
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
    item.nombre_cientifico = (request.form.get("nombre_cientifico") or "").strip()
    item.descripcion = (request.form.get("descripcion") or "").strip()
    item.habitat = (request.form.get("habitat") or "").strip()
    item.dieta = (request.form.get("dieta") or "").strip()
    item.zonas = (request.form.get("zonas") or "").strip()
    item.map_embed_url = (request.form.get("map_embed_url") or "").strip()
    item.museo_info = (request.form.get("museo_info") or "").strip()

    curiosidades_raw = (request.form.get("curiosidades") or "").strip()
    item.curiosidades = [x.strip() for x in curiosidades_raw.split("\n") if x.strip()]

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

# --------- CHAT API (RAG) ---------
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
        museum_context = "FRAGMENTOS RELEVANTES DEL MUSEO (RAG):\n" + "\n\n".join([f"- {c['text']}" for c in chunks])
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
    print("✅ DB inicializada")

@app.cli.command("create-admin")
def create_admin():
    username = os.getenv("ADMIN_USER", "admin")
    password = os.getenv("ADMIN_PASS", "admin123")
    with app.app_context():
        db.create_all()
        if User.query.filter_by(username=username).first():
            print("⚠️ Admin ya existe")
            return
        u = User(username=username, is_admin=True)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    print(f"✅ Admin creado: {username} / {password}")

@app.cli.command("create-user")
def create_user():
    username = os.getenv("USER_NAME", "user")
    password = os.getenv("USER_PASS", "user123")
    with app.app_context():
        db.create_all()
        if User.query.filter_by(username=username).first():
            print("⚠️ Usuario ya existe")
            return
        u = User(username=username, is_admin=False)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
    print(f"✅ Usuario creado: {username} / {password}")

@app.cli.command("seed")
def seed():
    with app.app_context():
        db.create_all()
        if db.session.get(Species, "condor-001"):
            print("⚠️ Seed ya aplicado")
            return
        sp = Species(
            id="condor-001",
            nombre_comun="Cóndor Andino",
            nombre_cientifico="Vultur gryphus",
            descripcion="Ave carroñera emblemática de los Andes.",
            habitat="Zonas montañosas andinas.",
            dieta="Carroña.",
            zonas="Andes (Colombia, Ecuador, Perú, Bolivia, Chile, Argentina).",
            map_embed_url="",
            museo_info="Dato del museo: símbolo cultural en varias regiones andinas."
        )
        sp.curiosidades = ["Planea largas distancias", "Aprovecha corrientes térmicas"]
        db.session.add(sp)
        db.session.commit()
        try:
            get_vs().reindex_species(sp.id, sp.museo_info)
        except Exception:
            pass
    print("✅ Seed aplicado")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)