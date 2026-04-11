import re

from models import Visit, Species, db


SPECIMEN_QUESTION_TERMS = (
    "este espécimen", "este especimen", "este ejemplar", "ejemplar",
    "espécimen", "especimen", "pieza", "pieza expuesta", "pieza exhibida",
    "expuesto", "exhibido", "museo", "vitrina", "colección", "coleccion",
    "sala", "procedencia", "origen", "de dónde viene", "de donde viene",
    "dónde fue encontrado", "donde fue encontrado", "fue encontrado",
    "hallado", "hallada", "hallaron", "recolectado", "recolectada",
    "colectado", "colectada", "capturado", "capturada", "donado",
    "donada", "ingresó al museo", "ingreso al museo", "registro",
    "inventario", "catalogado", "catalogada", "localidad", "sitio"
)

GENERAL_QUESTION_TERMS = (
    "hábitat", "habitat", "dieta", "qué come", "que come", "come",
    "distribución", "distribucion", "dónde vive", "donde vive", "vive",
    "familia", "orden", "reproducción", "reproduccion", "longevidad",
    "mide", "peso", "envergadura", "características", "caracteristicas",
    "ecología", "ecologia", "comportamiento", "estado de conservación",
    "estado de conservacion", "amenazas", "curiosidades"
)


def normalize_question(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def classify_question_scope(question: str) -> str:
    q = normalize_question(question)
    specimen_hits = sum(1 for term in SPECIMEN_QUESTION_TERMS if term in q)
    general_hits = sum(1 for term in GENERAL_QUESTION_TERMS if term in q)

    if specimen_hits and specimen_hits >= general_hits:
        return "specimen"
    if general_hits:
        return "general"
    return "mixed"


def build_structured_context(
    user_id: int | None,
    species: Species,
    question_scope: str = "mixed",
) -> str:
    parts = []
    parts.append("FICHA ESTRUCTURADA DEL ANIMAL ACTUAL (BD):")
    parts.append(f"ID QR: {species.qr_id}")
    parts.append(f"Nombre común: {species.nombre_comun}")
    if species.nombre_cientifico:
        parts.append(f"Nombre científico: {species.nombre_cientifico}")

    if question_scope == "specimen":
        parts.append(
            "Modo de respuesta detectado: pregunta sobre el espécimen/ejemplar exhibido. "
            "Los datos generales de distribución, hábitat o dieta NO deben usarse para inventar "
            "procedencia, hallazgo, colección o historia particular del ejemplar. "
            "Si el museo no aporta ese dato específico, debe decirse explícitamente."
        )
    else:
        parts.append("Modo de respuesta detectado: pregunta general sobre la especie.")
        if species.zonas:
            parts.append(f"Zonas donde se encuentra: {species.zonas}")
        if species.habitat:
            parts.append(f"Hábitat: {species.habitat}")
        if species.dieta:
            parts.append(f"Dieta: {species.dieta}")
        if species.descripcion:
            parts.append(f"Descripción: {species.descripcion}")
        if species.curiosidades:
            parts.append("Curiosidades: " + "; ".join(species.curiosidades))

    if user_id:
        last_visits = (
            db.session.query(Visit, Species)
            .join(Species, Species.id == Visit.species_id)
            .filter(Visit.user_id == user_id)
            .order_by(Visit.visited_at.desc())
            .limit(5)
            .all()
        )
        if last_visits:
            parts.append("\nRECORRIDO RECIENTE DEL USUARIO (últimas visitas):")
            for v, sp in last_visits:
                parts.append(f"- {sp.qr_id}: {sp.nombre_comun}")

    return "\n".join(parts)