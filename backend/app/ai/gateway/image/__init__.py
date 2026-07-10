"""Image-generation gateway tier (native Google GenAI, leak-safe).

Public surface: :func:`app.ai.gateway.image.service.generate_image`,
:func:`app.ai.gateway.image.service.image_enabled`, and
:class:`app.ai.gateway.image.service.ImageUnavailableError`.
"""

from app.ai.gateway.image.service import (  # noqa: F401
    ImageResult,
    ImageUnavailableError,
    generate_image,
    image_enabled,
)

__all__ = ["ImageResult", "ImageUnavailableError", "generate_image", "image_enabled"]
