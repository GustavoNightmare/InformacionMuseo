from models import Visit, Species, db

def build_structured_context(user_id: int | None, species: Species) -> str:
    parts = []
    parts.append("DATOS ESTRUCTURADOS DE LA ESPECIE (BD):")
    parts.append(f"ID QR: {species.qr_id}")
    parts.append(f"Nombre común: {species.nombre_comun}")
    if species.nombre_cientifico:
        parts.append(f"Nombre científico: {species.nombre_cientifico}")
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
