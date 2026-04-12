import sys

from app import Species, app, db, ensure_schema_updates, sync_species_to_tts


def main() -> int:
    with app.app_context():
        db.create_all()
        ensure_schema_updates()

        items = Species.query.order_by(Species.nombre_comun.asc(), Species.id.asc()).all()
        total = len(items)
        ok = 0
        failed: list[str] = []

        if total == 0:
            print("No hay especies para sincronizar.")
            return 0

        print(f"Sincronizando {total} especies con ServerTTS...")

        for index, item in enumerate(items, start=1):
            label = item.nombre_comun or item.id
            print(f"[{index}/{total}] {item.id} - {label}")
            try:
                sync_species_to_tts(item)
                ok += 1
                print("  OK")
            except Exception as exc:
                failed.append(f"{item.id}: {exc}")
                print(f"  ERROR: {exc}")

    print(f"\nSincronizadas {ok}/{total} especies con TTS.")
    if failed:
        print("Fallaron estas especies:")
        for line in failed:
            print(f" - {line}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
