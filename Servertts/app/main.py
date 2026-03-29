from __future__ import annotations
import time
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import cv2
import edge_tts
import httpx
import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse,HTMLResponse


load_dotenv()

app = FastAPI(
    title="Museo TTS Service",
    version="2.0.0",
    description="Recibe una imagen JPEG, detecta QR, consulta al principal y devuelve audio",
)

MUSEO_API_BASE_URL = os.getenv("MUSEO_API_BASE_URL", "").rstrip("/")
MUSEO_API_KEY = os.getenv("MUSEO_API_KEY", "")
MUSEO_TTS_PUBLIC_BASE_URL = os.getenv("MUSEO_TTS_PUBLIC_BASE_URL", "").rstrip("/")
TTS_API_KEY = os.getenv("TTS_API_KEY", "")

EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "es-CO-GonzaloNeural")
EDGE_TTS_RATE = os.getenv("EDGE_TTS_RATE", "+0%")
EDGE_TTS_VOLUME = os.getenv("EDGE_TTS_VOLUME", "+0%")

AUDIO_CACHE_DIR = os.getenv("AUDIO_CACHE_DIR", "./cache_audio")
Path(AUDIO_CACHE_DIR).mkdir(parents=True, exist_ok=True)
DEBUG_FRAMES_DIR = os.getenv("DEBUG_FRAMES_DIR", "./debug_frames")
Path(DEBUG_FRAMES_DIR).mkdir(parents=True, exist_ok=True)
ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
LAST_DEBUG_INFO = {
    "last_qr_text": "",
    "last_decode_method": "",
    "last_found": False,
    "last_error": "",
    "last_saved_frame": "",
    "last_timestamp": 0,
}

class TextToTTSRequest(BaseModel):
    text: str

def sanitize_id(value: str) -> str:
    return (value or "").strip()


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, list):
        return ". ".join([clean_text(v) for v in value if clean_text(v)])

    if isinstance(value, dict):
        return ". ".join([clean_text(v) for v in value.values() if clean_text(v)])

    text = str(value).strip()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

@app.post("/tts/from-text")
async def tts_from_text(
    payload: TextToTTSRequest,
    key: str | None = Query(default=None),
):
    if not TTS_API_KEY or key != TTS_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")

    text = clean_text(payload.text)
    if not text:
        raise HTTPException(status_code=400, detail="empty_text")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(tmp_fd)

    try:
        await generate_tts_file(text, tmp_path)
        audio_bytes = Path(tmp_path).read_bytes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"tts_generation_error: {str(e)}")
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={
            "X-TTS-Voice": EDGE_TTS_VOICE,
            "X-TTS-Text-Length": str(len(text)),
        },
    )

def normalize_curiosities(curiosities: Any) -> list[str]:
    if curiosities is None:
        return []

    if isinstance(curiosities, list):
        return [clean_text(x) for x in curiosities if clean_text(x)]

    if isinstance(curiosities, str):
        raw = curiosities.strip()
        if not raw:
            return []

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [clean_text(x) for x in parsed if clean_text(x)]
            if isinstance(parsed, dict):
                return [clean_text(v) for v in parsed.values() if clean_text(v)]
        except Exception:
            pass

        if ";" in raw:
            return [clean_text(x) for x in raw.split(";") if clean_text(x)]

        if "|" in raw:
            return [clean_text(x) for x in raw.split("|") if clean_text(x)]

        return [clean_text(raw)]

    return [clean_text(curiosities)]


def sentence(text: str) -> str:
    text = clean_text(text)
    if not text:
        return ""
    if text[-1] not in ".!?":
        text += "."
    return text


def join_sentences(parts: list[str]) -> str:
    return " ".join([sentence(p) for p in parts if clean_text(p)])

def pick_tts_fields(data: dict[str, Any]) -> dict[str, str]:
    return {
        "common_name": clean_text(data.get("common_name")),
        "scientific_name": clean_text(data.get("scientific_name")),
        "description": clean_text(data.get("description")),
        "habitat": clean_text(data.get("habitat")),
        "diet": clean_text(data.get("diet")),
        "geographic_distribution": clean_text(data.get("geographic_distribution")),
    }


def build_text_from_species(data: dict[str, Any], style: str = "ficha") -> str:
    data = pick_tts_fields(data)

    common_name = data["common_name"]
    scientific_name = data["scientific_name"]
    description = data["description"]
    habitat = data["habitat"]
    diet = data["diet"]
    geographic_distribution = data["geographic_distribution"]

    intro_name = common_name or "Este animal"

    if style == "corto":
        return join_sentences([
            intro_name,
            f"Su nombre científico es {scientific_name}" if scientific_name else "",
            description,
            f"Habita en {habitat}" if habitat else "",
            f"Su dieta es {diet}" if diet else "",
            f"Se encuentra en {geographic_distribution}" if geographic_distribution else "",
        ])

    if style == "narrativo":
        return join_sentences([
            f"Estás escuchando información sobre {intro_name}",
            f"Su nombre científico es {scientific_name}" if scientific_name else "",
            description,
            f"Su hábitat es {habitat}" if habitat else "",
            f"Su dieta es {diet}" if diet else "",
            f"Se distribuye en {geographic_distribution}" if geographic_distribution else "",
        ])

    return join_sentences([
        f"Nombre común: {common_name}" if common_name else "Especie del museo",
        f"Nombre científico: {scientific_name}" if scientific_name else "",
        f"Descripción: {description}" if description else "",
        f"Hábitat: {habitat}" if habitat else "",
        f"Dieta: {diet}" if diet else "",
        f"Distribución geográfica: {geographic_distribution}" if geographic_distribution else "",
    ])

def cache_key_for(qr_id: str, style: str, voice: str) -> str:
    raw = f"{qr_id}|{style}|{voice}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def decode_qr_from_jpeg_bytes(image_bytes: bytes) -> tuple[str | None, str]:
    if not image_bytes:
        return None, "empty_bytes"

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        return None, "cv2_imdecode_failed"

    detector = cv2.QRCodeDetector()

    # Intento 1: imagen color original
    qr_text, points, _ = detector.detectAndDecode(image)
    qr_text = sanitize_id(qr_text)
    if qr_text and ID_RE.fullmatch(qr_text):
        return qr_text, "color"

    # Intento 2: grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    qr_text, points, _ = detector.detectAndDecode(gray)
    qr_text = sanitize_id(qr_text)
    if qr_text and ID_RE.fullmatch(qr_text):
        return qr_text, "grayscale"

    # Intento 3: threshold binario
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    qr_text, points, _ = detector.detectAndDecode(thresh)
    qr_text = sanitize_id(qr_text)
    if qr_text and ID_RE.fullmatch(qr_text):
        return qr_text, "threshold_otsu"

    # Intento 4: agrandar imagen
    upscaled = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    qr_text, points, _ = detector.detectAndDecode(upscaled)
    qr_text = sanitize_id(qr_text)
    if qr_text and ID_RE.fullmatch(qr_text):
        return qr_text, "upscaled_gray"

    return None, "not_found"

def save_debug_frame(image_bytes: bytes, prefix: str = "last") -> str:
    timestamp = int(time.time())
    filename = f"{prefix}_{timestamp}.jpg"
    path = Path(DEBUG_FRAMES_DIR) / filename
    path.write_bytes(image_bytes)

    # también guarda una copia fija
    last_path = Path(DEBUG_FRAMES_DIR) / "last_frame.jpg"
    last_path.write_bytes(image_bytes)

    return str(path)

async def fetch_species_from_main_server(qr_id: str) -> dict[str, Any]:
    if not MUSEO_API_BASE_URL:
        raise RuntimeError("MUSEO_API_BASE_URL no está configurado")

    if not MUSEO_API_KEY:
        raise RuntimeError("MUSEO_API_KEY no está configurado")

    url = f"{MUSEO_API_BASE_URL}/api/public/species/{qr_id}/tts"
    headers = {"X-API-Key": MUSEO_API_KEY}

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers=headers)

    if response.status_code == 401:
        raise HTTPException(status_code=502, detail="main_server_unauthorized")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="species_not_found")
    if response.status_code >= 500:
        raise HTTPException(status_code=502, detail="main_server_error")
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"unexpected_main_server_status_{response.status_code}",
        )

    try:
        data = response.json()
    except Exception:
        raise HTTPException(status_code=502, detail="invalid_main_server_json")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="invalid_main_server_payload")

    return data


async def generate_tts_file(text: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice=EDGE_TTS_VOICE,
        rate=EDGE_TTS_RATE,
        volume=EDGE_TTS_VOLUME,
    )
    await communicate.save(output_path)


async def ensure_audio_file_for_qr(qr_id: str, style: str) -> tuple[str, dict[str, Any], str]:
    species_data = await fetch_species_from_main_server(qr_id)
    text = build_text_from_species(species_data, style=style)

    if not text.strip():
        raise HTTPException(status_code=422, detail="empty_tts_text")

    file_hash = cache_key_for(qr_id, style, EDGE_TTS_VOICE)
    output_path = os.path.join(AUDIO_CACHE_DIR, f"{file_hash}.mp3")

    if os.path.exists(output_path):
        return output_path, species_data, text

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
    os.close(tmp_fd)

    try:
        await generate_tts_file(text, tmp_path)
        Path(tmp_path).replace(output_path)
    except Exception as e:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"tts_generation_error: {str(e)}")

    return output_path, species_data, text


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "museo-tts",
        "voice": EDGE_TTS_VOICE,
    }


@app.get("/tts/by-qr/{qr_id}")
async def tts_by_qr(
    qr_id: str,
    style: str = Query(default="ficha", pattern="^(ficha|narrativo|corto)$"),
    key: str | None = Query(default=None),
):
    if not TTS_API_KEY or key != TTS_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")

    qr_id = sanitize_id(qr_id)
    if not qr_id or not ID_RE.fullmatch(qr_id):
        raise HTTPException(status_code=400, detail="invalid_qr_id")

    output_path, _, _ = await ensure_audio_file_for_qr(qr_id, style)

    return FileResponse(
        output_path,
        media_type="audio/mpeg",
        filename=f"{qr_id}.mp3",
        headers={
            "X-TTS-QR": qr_id,
            "X-TTS-Style": style,
        },
    )

@app.post("/qr/resolve-frame")
async def qr_resolve_frame(
    request: Request,
    style: str = Query(default="ficha", pattern="^(ficha|narrativo|corto)$"),
    key: str | None = Query(default=None),
):
    if not TTS_API_KEY or key != TTS_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")

    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="empty_image")

    saved_path = save_debug_frame(image_bytes, prefix="incoming")

    qr_id, decode_method = decode_qr_from_jpeg_bytes(image_bytes)

    LAST_DEBUG_INFO["last_qr_text"] = qr_id or ""
    LAST_DEBUG_INFO["last_decode_method"] = decode_method
    LAST_DEBUG_INFO["last_found"] = bool(qr_id)
    LAST_DEBUG_INFO["last_error"] = "" if qr_id else "qr_not_found_in_frame"
    LAST_DEBUG_INFO["last_saved_frame"] = saved_path
    LAST_DEBUG_INFO["last_timestamp"] = int(time.time())

    print(f"[QR DEBUG] saved_frame={saved_path}")
    print(f"[QR DEBUG] decode_method={decode_method}")
    print(f"[QR DEBUG] qr_id={qr_id}")

    if not qr_id:
        return JSONResponse(
            status_code=404,
            content={
                "found": False,
                "error": "qr_not_found_in_frame",
                "decode_method": decode_method,
                "debug_frame_url": "/debug/last-frame",
            },
        )

    species_data = await fetch_species_from_main_server(qr_id)
    filtered_data = pick_tts_fields(species_data)
    text = build_text_from_species(filtered_data, style=style)

    if not text.strip():
        raise HTTPException(status_code=422, detail="empty_tts_text")

    return JSONResponse({
        "found": True,
        "qr_id": qr_id,
        "text": text,
        "fields": filtered_data,
        "decode_method": decode_method,
        "debug_frame_url": "/debug/last-frame",
    })

@app.get("/debug/view", response_class=HTMLResponse)
async def debug_view():
    html = f"""
    <html>
      <head>
        <title>Museo TTS Debug</title>
        <meta http-equiv="refresh" content="3">
        <style>
          body {{ font-family: Arial, sans-serif; margin: 20px; }}
          img {{ max-width: 90vw; border: 1px solid #ccc; }}
          pre {{ background: #f5f5f5; padding: 12px; }}
        </style>
      </head>
      <body>
        <h1>Última imagen recibida</h1>
        <img src="/debug/last-frame?t={int(time.time())}" />
        <h2>Estado</h2>
        <pre>{json.dumps(LAST_DEBUG_INFO, indent=2, ensure_ascii=False)}</pre>
      </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/debug/last-frame")
async def debug_last_frame():
    last_path = Path(DEBUG_FRAMES_DIR) / "last_frame.jpg"
    if not last_path.exists():
        raise HTTPException(status_code=404, detail="no_debug_frame_yet")

    return FileResponse(str(last_path), media_type="image/jpeg")
@app.get("/debug/last-status")
async def debug_last_status():
    return JSONResponse(LAST_DEBUG_INFO)

@app.post("/tts/from-frame")
async def tts_from_frame(
    request: Request,
    style: str = Query(default="ficha", pattern="^(ficha|narrativo|corto)$"),
    key: str | None = Query(default=None),
):
    if not TTS_API_KEY or key != TTS_API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")

    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="empty_image")

    qr_id, decode_method = decode_qr_from_jpeg_bytes(image_bytes)
    if not qr_id:
        return JSONResponse(
            status_code=404,
            content={"found": False, "error": "qr_not_found_in_frame"},
        )

    output_path, _, _ = await ensure_audio_file_for_qr(qr_id, style)

    return FileResponse(
        output_path,
        media_type="audio/mpeg",
        filename=f"{qr_id}.mp3",
        headers={
            "X-TTS-QR": qr_id,
            "X-TTS-Style": style,
        },
    )