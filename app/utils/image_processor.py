import asyncio
import base64
import io

from ..config import config
from .http_client import get_session

# Tipos MIME de imagem aceitos por OpenRouter
ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]

# Anexo de centenas de MB (ate 10 por mensagem) ficava inteiro em memoria duas vezes:
# os bytes baixados e a copia em base64. Acima disso a imagem e ignorada.
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
# Limites de decodificacao: pixels por imagem e anexos processados por mensagem.
MAX_IMAGE_PIXELS = 25_000_000
MAX_ATTACHMENTS_PER_MESSAGE = 4

# Pillow e opcional: sem ele o bot continua funcionando, so manda a imagem no tamanho
# original (o que gasta muito mais token e pode estourar o limite da requisicao).
try:
    import warnings

    from PIL import Image

    # Bomba de descompressao: um PNG pequeno pode virar centenas de MB de RAM ao
    # decodificar. Acima do limite de pixels vira erro (tratado como imagem invalida)
    # em vez de so aviso.
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)

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


_STICKER_MIME = {"png": "image/png", "apng": "image/png", "gif": "image/gif"}


class _Source:
    """Imagem a baixar. content_type None = desconhecido: vale o que o servidor disser."""

    def __init__(self, url, filename, content_type=None, size=0):
        self.url = url
        self.filename = filename
        self.content_type = content_type
        self.size = size


def image_sources(attachments, embeds=(), stickers=()):
    """Tudo que a mensagem mostra como imagem: anexos, GIF/imagem de link (embed) e figurinha.

    Embed usa so o proxy_url do Discord: a URL original e de terceiro e baixar dela pelo
    bot saltaria validate_fetch_url (SSRF). Embed sem proxy_url (webhook, outro app) e
    ignorado. Entram so os tipos image/gifv (Tenor, Giphy, link de imagem); previa de
    artigo ou video e capa, nao o conteudo que a pessoa mandou.
    Figurinha lottie e vetorial animada e nao tem como virar imagem aqui.
    """
    sources = [
        _Source(a.url, a.filename, a.content_type, getattr(a, "size", 0) or 0)
        for a in attachments
        if getattr(a, "content_type", None) in ALLOWED_TYPES
    ]
    for e in embeds:
        if getattr(e, "type", None) not in ("image", "gifv"):
            continue
        media = getattr(e, "thumbnail", None) or getattr(e, "image", None)
        url = getattr(media, "proxy_url", None)
        if url:
            sources.append(_Source(url, url.split("?")[0].rsplit("/", 1)[-1] or "gif"))
    for s in stickers:
        mime = _STICKER_MIME.get(getattr(getattr(s, "format", None), "name", ""))
        if mime:
            sources.append(_Source(s.url, f"{s.name}.png" if mime == "image/png" else f"{s.name}.gif", mime))
    return sources[:MAX_ATTACHMENTS_PER_MESSAGE]


async def _process_attachment(session, attachment):
    declared = attachment.content_type
    if declared is not None and declared not in ALLOWED_TYPES:
        return None

    if attachment.size > MAX_ATTACHMENT_BYTES:
        print(f"[imagens] {attachment.filename} ignorado: {attachment.size} bytes acima do limite.")
        return None

    try:
        async with session.get(attachment.url) as res:
            if not res.ok:
                raise RuntimeError(f"HTTP {res.status}")
            content_type = declared or (res.content_type or "").lower()
            if content_type not in ALLOWED_TYPES:
                return None
            if (res.content_length or 0) > MAX_ATTACHMENT_BYTES:
                print(f"[imagens] {attachment.filename} ignorado: acima do limite.")
                return None
            data = await res.read()

        # Processamento no Pillow e CPU-bound: roda em thread dedicada para nao
        # travar o event loop do Discord.
        shrunk, mime_type = await asyncio.to_thread(_shrink, data, content_type)

        return {
            "base64": base64.b64encode(shrunk).decode("ascii"),
            "mime_type": mime_type,
            "name": attachment.filename,
            "data": data,
        }
    except Exception as err:  # noqa: BLE001 - mirrors JS catch-all
        print(f"[imagens] Falha ao baixar {attachment.filename}: {err}")
        return None


async def extract_images(sources):
    """Baixa as imagens (de image_sources) concorrentemente e devolve base64 pronto para o modelo.

    Guarda tambem os bytes crus em 'data', que o OCR usa - o OCR le melhor a imagem
    original do que a versao reduzida.
    """
    if not sources:
        return []

    session = await get_session()
    results = await asyncio.gather(*[_process_attachment(session, s) for s in sources])
    return [r for r in results if r is not None]
