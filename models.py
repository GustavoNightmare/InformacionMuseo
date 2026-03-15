from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # NUEVO
    nombre = db.Column(db.String(120), nullable=False)
    edad = db.Column(db.Integer, nullable=False)

    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Species(db.Model):
    id = db.Column(db.String(64), primary_key=True)

    nombre_comun = db.Column(db.String(200), nullable=False)
    nombre_cientifico = db.Column(db.String(200), nullable=True)

    familia = db.Column(db.String(120), nullable=True)
    orden = db.Column(db.String(120), nullable=True)

    descripcion = db.Column(db.Text, nullable=True)
    habitat = db.Column(db.Text, nullable=True)
    dieta = db.Column(db.Text, nullable=True)

    zonas = db.Column(db.Text, nullable=True)
    map_embed_url = db.Column(db.String(600), nullable=True)

    imagen = db.Column(db.String(300), nullable=True)
    audio = db.Column(db.String(300), nullable=True)

    museo_info = db.Column(db.Text, nullable=True)

    curiosidades_json = db.Column(db.Text, nullable=True)

    # Ajuste visual SOLO para la miniatura/listado
    thumb_pos_x = db.Column(db.Integer, nullable=False, default=50)
    thumb_pos_y = db.Column(db.Integer, nullable=False, default=50)
    thumb_zoom = db.Column(db.Integer, nullable=False, default=100)

    @property
    def curiosidades(self):
        if not self.curiosidades_json:
            return []
        try:
            return json.loads(self.curiosidades_json)
        except Exception:
            return []

    @curiosidades.setter
    def curiosidades(self, value):
        self.curiosidades_json = json.dumps(value or [], ensure_ascii=False)


class MuseumDoc(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    species_id = db.Column(db.String(64), db.ForeignKey(
        "species.id"), nullable=False)

    stored_path = db.Column(db.String(400), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    extracted_text = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False)


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    species_id = db.Column(db.String(64), db.ForeignKey(
        "species.id"), nullable=False)
    visited_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False)


# NUEVO: memoria de chat por usuario + especie
class ChatTurn(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    species_id = db.Column(db.String(64), db.ForeignKey(
        "species.id"), nullable=False)

    role = db.Column(db.String(20), nullable=False)  # "user" | "assistant"
    content = db.Column(db.Text, nullable=False)

    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False)
