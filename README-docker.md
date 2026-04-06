# InformacionMuseo con Docker, Ollama, ServerTTS y ngrok

Este stack deja el proyecto listo con 5 servicios:

- `museo-app`: aplicación Flask principal.
- `ollama`: LLM local (chat + embeddings).
- `ngrok`: túnel HTTPS para la app principal.
- `servertts`: API FastAPI para TTS y resolución de QR por frame.
- `ngrok-tts`: túnel HTTPS dedicado para `servertts` con otro token.

## 1) Preparar variables

```bash
cp .env.example .env
```

Edita `.env` y completa como mínimo:

- `SECRET_KEY`
- `ADMIN_USER`
- `ADMIN_PASS`
- `MUSEO_TTS_SHARED_KEY` (clave compartida entre Flask y servertts)
- `TTS_API_KEY` (clave para consumidores del TTS)
- `NGROK_AUTHTOKEN` (cuenta ngrok del sistema principal)
- `NGROK_TTS_AUTHTOKEN` (otra cuenta/token para el túnel de TTS)

Opcional pero recomendado:

- `MUSEO_TTS_PUBLIC_BASE_URL` = URL HTTPS pública de `ngrok-tts`.

## 2) Levantar todo

```bash
docker compose up -d --build
```

La primera vez, `ollama` intentará descargar modelos (chat y embeddings),
por lo que puede tardar bastante según red y hardware.

## 3) Servicios y puertos

- App principal local: `http://IP_O_HOST:5000`
- Inspector ngrok principal: `http://IP_O_HOST:4040`
- ServerTTS local: `http://IP_O_HOST:8010`
- Inspector ngrok TTS: `http://IP_O_HOST:4041`

Health checks rápidos:

```bash
curl http://IP_O_HOST:5000
curl http://IP_O_HOST:8010/health
```

## 4) Obtener URLs HTTPS públicas

Logs del ngrok principal:

```bash
docker compose logs -f ngrok
```

Logs del ngrok dedicado a TTS:

```bash
docker compose logs -f ngrok-tts
```

Cada uno publicará su propia URL HTTPS en logs e inspector.

## 5) Cómo queda la integración TTS

- `servertts` consulta al Flask por:
  - `GET /api/public/species/<qr_id>/tts`
- Para autorizarse contra Flask usa:
  - `MUSEO_API_KEY = MUSEO_TTS_SHARED_KEY`
- Para autorizar clientes contra `servertts` usa:
  - `TTS_API_KEY`

En Docker Compose, `servertts` apunta automáticamente a:

- `MUSEO_API_BASE_URL=http://museo-app:5000`

## 6) Persistencia

Estos datos se mantienen en carpetas del proyecto:

- `instance/` -> SQLite
- `chroma_db/` -> ChromaDB
- `static/uploads/` -> archivos subidos
- `ollama/` -> modelos descargados de Ollama
- `Servertts/cache_audio/` -> audios MP3 cacheados
- `Servertts/debug_frames/` -> imágenes para depuración QR

## 7) Comandos útiles

Parar servicios:

```bash
docker compose down
```

Ver logs por servicio:

```bash
docker compose logs -f museo-app
docker compose logs -f ollama
docker compose logs -f servertts
docker compose logs -f ngrok
docker compose logs -f ngrok-tts
```

Recrear servicios:

```bash
docker compose up -d --build --force-recreate
```

## 8) Pruebas rápidas para TTS

Probar endpoint de audio por QR (local):

```bash
curl "http://IP_O_HOST:8010/tts/by-qr/condor-001?key=TU_TTS_API_KEY"
```

Probar resolución de frame (POST binario JPEG):

```bash
curl -X POST "http://IP_O_HOST:8010/qr/resolve-frame?key=TU_TTS_API_KEY" \
  --data-binary "@frame.jpg" \
  -H "Content-Type: image/jpeg"
```

## 9) Si ngrok o ngrok-tts no levantan

Verifica tokens en `.env`:

- `NGROK_AUTHTOKEN`
- `NGROK_TTS_AUTHTOKEN`

Reinicia solo el servicio afectado:

```bash
docker compose up -d ngrok
docker compose up -d ngrok-tts
```

## 10) Notas para Orange Pi 4 Pro

- Usa sistema operativo de 64 bits.
- La primera construcción puede tardar varios minutos.
- Si hay presión de RAM/CPU, reduce workers en `.env`:

```env
GUNICORN_WORKERS=1
GUNICORN_THREADS=2
```
