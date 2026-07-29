import base64

import aiohttp

# Tipos MIME de imagem aceitos por OpenRouter
ALLOWED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]


async def extract_images(attachments):
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

                images.append(
                    {
                        "base64": base64.b64encode(data).decode("ascii"),
                        "mime_type": content_type,
                        "name": attachment.filename,
                    }
                )
            except Exception as err:  # noqa: BLE001 - mirrors JS catch-all
                print(f"[imageProcessor] Falha ao baixar imagem {attachment.filename}: {err}")

    return images


def has_images(attachments):
    return any(getattr(a, "content_type", None) in ALLOWED_TYPES for a in attachments)
