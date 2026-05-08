import os
from pathlib import Path
from typing import List, Optional

from lazyllm.common import retry
from lazyllm.thirdparty import PIL, fsspec
from lazyllm.tools.rag.doc_node import ImageDocNode
from lazyllm.tools.rag.readers.readerBase import LazyLLMReaderBase, get_default_fs

from config import config as _cfg

RETRY_TIMES = 3


class ImageEmbReader(LazyLLMReaderBase):
    __lazyllm_registry_disable__ = True

    def __init__(self, return_trace: bool = True) -> None:
        super().__init__(return_trace=return_trace)

    def _normalized_root(self) -> Path:
        return Path(_cfg['shared_upload_dir']) / 'normalized_images'

    def _safe_name(self, value: str) -> str:
        normalized = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in value.strip())
        return normalized or 'image'

    def _normalize_image_file(self, image_path: str) -> str:
        src = Path(image_path).resolve()
        target_dir = self._normalized_root() / self._safe_name(src.parent.name or 'root')
        target_dir.mkdir(parents=True, exist_ok=True)
        dst = target_dir / f'{self._safe_name(src.stem)}.jpg'

        with PIL.Image.open(src) as img:
            if getattr(img, 'n_frames', 1) > 1:
                img.seek(0)

            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                rgba = img.convert('RGBA')
                background = PIL.Image.new('RGB', rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.getchannel('A'))
                rgb = background
            else:
                rgb = img.convert('RGB')

            rgb.save(dst, format='JPEG', quality=95)
        return str(dst)

    @retry(stop_after_attempt=RETRY_TIMES)
    def _load_data(self, file: Path, fs: Optional['fsspec.AbstractFileSystem'] = None) -> List[ImageDocNode]:
        if not isinstance(file, Path):
            file = Path(file)

        suffix = file.suffix.lower()
        fs = fs or get_default_fs()
        file_name = file.name
        abs_path = os.path.abspath(str(file))
        normalized_path = self._normalize_image_file(abs_path)

        metadata = {
            'source_path': abs_path,
            'normalized_source_path': normalized_path,
            'file_name': file_name,
            'file_ext': suffix,
            'file_type': 'image',
            'is_pure_image': True,
        }
        return [ImageDocNode(image_path=normalized_path, metadata=metadata)]


__all__ = ['ImageEmbReader']
