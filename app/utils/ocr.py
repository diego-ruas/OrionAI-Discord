"""Leitura de texto em imagens, feita localmente com Tesseract.

Print de codigo, mensagem de erro, recorte de conversa: a maior parte das imagens que
aparecem num Discord e texto, e para essas nao ha motivo de mandar a imagem inteira
para um modelo de visao na nuvem. O OCR roda em menos de um segundo, com uns 100 MB de
RAM, e o conteudo nao sai da rede local.

Nao substitui um modelo de visao: nao descreve cena, nao entende foto, nao interpreta
grafico. Por isso o resultado so e usado quando ha texto suficiente (config.ocr_min_chars).
"""

import io

from ..config import config

try:
    import pytesseract
    from PIL import Image

    OCR_IMPORTS_OK = True
except ImportError:  # pragma: no cover - ambiente sem as libs
    pytesseract = None
    Image = None
    OCR_IMPORTS_OK = False

# O binario do tesseract e separado da lib Python; a checagem so acontece no primeiro
# uso, e o resultado fica em cache para nao pagar o custo a cada imagem.
_binary_ok = None


def available():
    global _binary_ok

    if not config.ocr_enabled or not OCR_IMPORTS_OK:
        return False

    if _binary_ok is None:
        try:
            pytesseract.get_tesseract_version()
            _binary_ok = True
        except Exception as err:  # noqa: BLE001 - binario ausente ou quebrado
            print(f"[ocr] Tesseract indisponivel ({err}); OCR desligado.")
            _binary_ok = False

    return _binary_ok


def extract_text(data):
    """Devolve o texto encontrado na imagem, ou string vazia."""
    if not available():
        return ""

    try:
        with Image.open(io.BytesIO(data)) as img:
            if getattr(img, "is_animated", False):
                img.seek(0)
            # Escala de cinza ajuda o Tesseract e e mais barato que a imagem colorida.
            text = pytesseract.image_to_string(img.convert("L"), lang=config.ocr_langs)
    except Exception as err:  # noqa: BLE001 - imagem ruim ou idioma nao instalado
        print(f"[ocr] Falha ao ler imagem: {err}")
        return ""

    # O Tesseract enche o resultado de linhas em branco quando a imagem tem espaco vazio.
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line.strip())
    return cleaned.strip()


def looks_like_text(text):
    """Se ha texto suficiente, a imagem pode ser respondida sem modelo de visao."""
    return len(text) >= config.ocr_min_chars
