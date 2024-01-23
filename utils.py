from base64 import b64decode, b64encode
from io import BytesIO


def encode_image(image_bytes: str) -> str:
    return b64encode(image_bytes).decode()


def decode_image(image_b64: str) -> BytesIO:
    return BytesIO(b64decode(image_b64))
