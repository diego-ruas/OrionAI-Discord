import base64
import io

import aiohttp

from ..config import config

# Tipos MIME de imagem aceitos por OpenRouter
ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]

# Pillow e opcional: sem ele o bot continua funcionando, so manda a imagem no tamanho
# original (o que gasta muito mais token e pode estourar o limite da requisicao).
try:
    from PIL import Image

    PILLOW_AVAILABLE = True
except ImportError:  # pragma: no cover - ambiente sem Pillow
    Image = None
    PILLOW_AVAILABLE = False
    print("[imagens] Pillow ausente: imagens serao enviadas no tamanho original.")


def _shrink(data, content_type):
    """Reduz a imagem para caber em VISION_MAX_IMAGE_PX e recomprime como JPEG.

    Uma foto de celular tem uns 4 MB, que viram ~5,3 MB depois do base64 - muito mais
    do que qualquer modelo precisa para entender a cena, e o suficiente para estourar
    limite de requisicao. Devolve (bytes, mime_type).
    """
    if not PILLOW_AVAILABLE or config.vision_max_image_px <= 0:
        return data, content_type

    try:
        with Image.open(io.BytesIO(data)) as img:
            # GIF animado: so o primeiro quadro interessa para o modelo.
            if getattr(img, "is_animated", False):
                img.seek(0)

            largest = max(img.size)
            needs_resize = largest > config.vision_max_image_px

            if img.mode in ("RGBA", "LA", "P"):
                # JPEG nao tem canal alfa; achata sobre branco para nao virar fundo preto.
                background = Image.new("RGB", img.size, (255, 255, 255))
                converted = img.convert("RGBA")
                background.paste(converted, mask=converted.split()[-1])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            if needs_resize:
                ratio = config.vision_max_image_px / largest
                new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
                img = img.resize(new_size, Image.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=config.vision_jpeg_quality, optimize=True)
            shrunk = buffer.getvalue()
    except Exception as err:  # noqa: BLE001 - imagem corrompida ou formato exotico
        print(f"[imagens] Falha ao redimensionar ({err}), enviando original.")
        return data, content_type

    # Se a recompressao nao ajudou (imagem ja pequena), fica com a original.
    if len(shrunk) >= len(data):
        return data, content_type

    print(
        f"[imagens] {len(data) // 1024} KB -> {len(shrunk) // 1024} KB "
        f"(max {config.vision_max_image_px}px)"
    )
    return shrunk, "image/jpeg"


async def extract_images(attachments):
    """Baixa os anexos de imagem e devolve base64 pronto para o modelo de visao.

    Guarda tambem os bytes crus em 'data', que o OCR usa - o OCR le melhor a imagem
    original do que a versao reduzida.
    """
    images = []

    async with aiohttp.ClientSession() as session:
        for attachment in attachments:
            content_type = getattr(attachment, "content_type", None)
            if content_type not in ALLOWED_TYPES:
                continue

            try:
                async with session.get(attachment.url) as res:
                    if not res.ok:
                        raise RuntimeError(f"HTTP {res.status}")
                    data = await res.read()

                shrunk, mime_type = _shrink(data, content_type)

                images.append(
                    {
                        "base64": base64.b64encode(shrunk).decode("ascii"),
                        "mime_type": mime_type,
                        "name": attachment.filename,
                        "data": data,
                    }
                )
            except Exception as err:  # noqa: BLE001 - mirrors JS catch-all
                print(f"[imagens] Falha ao baixar {attachment.filename}: {err}")

    return images


def has_images(attachments):
    return any(getattr(a, "content_type", None) in ALLOWED_TYPES for a in attachments)
