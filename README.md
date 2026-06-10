# 🏛️ InformacionMuseo

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![Flask](https://img.shields.io/badge/flask-%23000.svg?style=for-the-badge&logo=flask&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-000?style=for-the-badge&logo=ollama&logoColor=white)

Un sistema inteligente, interactivo y autónomo para la gestión e información de museos. Integra un backend robusto en **Flask** con capacidades RAG impulsadas por **Ollama** y **ChromaDB**, además de un servidor de **Text-to-Speech (TTS)** y resolución de **Códigos QR** usando **FastAPI**.

---

## 📑 Tabla de Contenidos

- [Características Principales](#-características-principales)
- [Arquitectura del Sistema](#-arquitectura-del-sistema)
- [Requisitos Previos](#-requisitos-previos)
- [Instalación y Configuración](#-instalación-y-configuración)
- [Uso con Docker](#-uso-con-docker)
- [Uso de la API y Servicios](#-uso-de-la-api-y-servicios)
- [Persistencia de Datos](#-persistencia-de-datos)
- [Comandos Útiles](#-comandos-útiles)

---

## ✨ Características Principales

- 🤖 **IA y RAG Integrado:** Búsqueda y respuestas inteligentes sobre especies u objetos de exhibición mediante Ollama y ChromaDB.
- 🗣️ **Text-to-Speech (TTS):** Microservicio dedicado para generar audios a partir de la información de las exhibiciones, ideal para guías de audio interactivas.
- 📱 **Resolución de QR:** Escaneo y detección de información mediante imágenes (frames) de códigos QR.
- 🐳 **Dockerizado:** Despliegue con un solo comando gracias a Docker Compose, orquestando 5 servicios conectados.
- 🌐 **Exposición Segura:** Integración nativa con `ngrok` para túneles HTTPS tanto para la app web como para el servicio TTS.

---

## 🏗️ Arquitectura del Sistema

El ecosistema se compone de 5 servicios corriendo simultáneamente:

1. **`museo-app`**: Aplicación Flask principal que maneja la lógica de negocio, base de datos (SQLite) y panel de administración.
2. **`ollama`**: Motor de IA local para chats y *embeddings*.
3. **`servertts`**: API en FastAPI encargada de la generación de voz (TTS) y procesamiento visual de QR.
4. **`ngrok`**: Túnel para exponer la app principal de manera segura (HTTPS).
5. **`ngrok-tts`**: Túnel HTTPS dedicado exclusivamente al servidor TTS.

---

## ⚙️ Requisitos Previos

- [Docker](https://docs.docker.com/get-docker/) y [Docker Compose](https://docs.docker.com/compose/install/)
- Cuenta en [ngrok](https://ngrok.com/) y uno o dos AuthTokens (según si usas el mismo o diferentes para la app y el TTS).

---

## 🚀 Instalación y Configuración

1. **Clona el repositorio**
   ```bash
   git clone https://github.com/tu-usuario/InformacionMuseo.git
   cd InformacionMuseo
   ```

2. **Prepara las variables de entorno**
   Copia el archivo de ejemplo para crear tu configuración local:
   ```bash
   cp .env.example .env
   ```

   Edita el `.env` y completa los valores clave:
   - `SECRET_KEY`, `ADMIN_USER`, `ADMIN_PASS`
   - `MUSEO_TTS_SHARED_KEY`: Clave compartida entre Flask y ServerTTS.
   - `TTS_API_KEY`: Clave de protección para los endpoints de TTS.
   - `NGROK_AUTHTOKEN` y `NGROK_TTS_AUTHTOKEN` para los túneles.

---

## 🐳 Uso con Docker

Levantar el stack completo es tan sencillo como:

```bash
docker compose up -d --build
```
> **Nota:** La primera vez, `ollama` descargará los modelos de lenguaje y embeddings necesarios. Este proceso puede tardar dependiendo de tu conexión a internet.

### 🌐 Accesos y Puertos (Local)
- **App Web Principal:** `http://localhost:5000`
- **Server TTS:** `http://localhost:8010`
- **Inspector ngrok (App):** `http://localhost:4040`
- **Inspector ngrok (TTS):** `http://localhost:4041`

---

## 📡 Uso de la API y Servicios

### Obtener URLs Públicas (ngrok)
Para ver los enlaces HTTPS públicos generados:
```bash
# Logs del túnel de la app
docker compose logs -f ngrok

# Logs del túnel TTS
docker compose logs -f ngrok-tts
```

### Endpoints Útiles
Probar generación de audio por QR (local):
```bash
curl "http://localhost:8010/tts/by-qr/ejemplo-qr-001?key=TU_TTS_API_KEY"
```

Probar resolución de QR desde una imagen (JPEG):
```bash
curl -X POST "http://localhost:8010/qr/resolve-frame?key=TU_TTS_API_KEY" \
  --data-binary "@frame.jpg" \
  -H "Content-Type: image/jpeg"
```

---

## 💾 Persistencia de Datos

El proyecto usa volúmenes y carpetas locales para evitar pérdida de datos al reiniciar los contenedores:
- `instance/`: Base de datos SQLite.
- `chroma_db/`: Base de datos vectorial (Chroma).
- `static/uploads/`: Archivos multimedia subidos por los administradores.
- `ollama/`: Modelos de IA descargados.
- `Servertts/cache_audio/`: Caché de audios MP3 generados.
- `Servertts/debug_frames/`: Imágenes temporales para escaneo QR.

---

## 🛠️ Comandos Útiles

- **Ver logs de un servicio:**
  ```bash
  docker compose logs -f museo-app
  ```
- **Detener todos los servicios:**
  ```bash
  docker compose down
  ```
- **Reconstruir y forzar reinicio de contenedores:**
  ```bash
  docker compose up -d --build --force-recreate
  ```

---

<p align="center">
  <b>Hecho con ❤️ para la modernización e interactividad en Museos.</b>
</p>
