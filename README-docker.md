# InformacionMuseo con Docker, Ollama y ngrok

Este paquete deja el proyecto listo para correr con 3 servicios:

- `museo-app`: aplicación Flask
- `ollama`: LLM local (`qwen3.5:4b`) + embeddings (`nomic-embed-text`)
- `ngrok`: túnel HTTPS para acceder desde el celular y permitir cámara

## 1. Preparar variables

```bash
cp .env.example .env
```

Edita `.env` y coloca por lo menos:

- `SECRET_KEY`
- `ADMIN_USER`
- `ADMIN_PASS`
- `NGROK_AUTHTOKEN`

## 2. Levantar todo

```bash
docker compose up -d --build
```

La primera vez, el servicio `ollama` intentará descargar automáticamente:

- `qwen3.5:4b`
- `nomic-embed-text`

Eso puede tardar bastante en la Orange Pi según la red y el almacenamiento.

## 3. Ver la aplicación

En la red local:

```text
http://IP_DE_TU_ORANGE_PI:5000
```

## 4. Ver la URL HTTPS de ngrok

Puedes verla con cualquiera de estas opciones:

```bash
docker compose logs -f ngrok
```

O entrando al inspector web de ngrok:

```text
http://IP_DE_TU_ORANGE_PI:4040
```

La URL pública HTTPS es la que debes abrir en el celular para que la cámara funcione.

## 5. Persistencia

Estos datos quedan guardados en carpetas del proyecto:

- `instance/` -> SQLite
- `chroma_db/` -> ChromaDB
- `static/uploads/` -> archivos subidos
- `ollama/` -> modelos descargados de Ollama

## 6. Comandos útiles

Parar servicios:

```bash
docker compose down
```

Ver logs:

```bash
docker compose logs -f museo-app
docker compose logs -f ollama
docker compose logs -f ngrok
```

Recrear contenedores:

```bash
docker compose up -d --build --force-recreate
```

## 7. Notas para Orange Pi 4 Pro

- Usa un sistema operativo de 64 bits.
- Es mejor instalar Docker y Docker Compose Plugin directamente en la Orange Pi.
- La primera construcción puede tardar varios minutos.
- Si la RAM o la temperatura te dan problemas, reduce workers en `.env`:

```env
GUNICORN_WORKERS=1
GUNICORN_THREADS=2
```

## 8. Si ngrok no levanta

Revisa que `NGROK_AUTHTOKEN` esté correcto en `.env`.

Luego reinicia solo ngrok:

```bash
docker compose up -d ngrok
```
