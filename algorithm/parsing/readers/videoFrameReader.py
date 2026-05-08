import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from lazyllm.thirdparty import fsspec
from lazyllm.tools.rag.doc_node import ImageDocNode
from lazyllm.tools.rag.readers.readerBase import LazyLLMReaderBase, get_default_fs, is_default_fs

from config import config as _cfg
from parsing.readers.imageEmbReader import ImageEmbReader

FRAME_DIR = Path(tempfile.gettempdir()) / 'lazyrag_video_frames'


class VideoFrameReader(LazyLLMReaderBase):
    __lazyllm_registry_disable__ = True

    def __init__(self, time: Optional[float] = None, return_trace: bool = True) -> None:
        super().__init__(return_trace=return_trace)
        time_value = time if time is not None else float(_cfg['video_frame_interval'])
        if time_value <= 0:
            raise ValueError('`time` must be greater than 0.')
        self._time = time_value
        self._image_reader = ImageEmbReader(return_trace=return_trace)

    def _safe_name(self, value: str) -> str:
        normalized = ''.join(c if c.isalnum() or c in ('-', '_') else '_' for c in value.strip())
        return normalized or 'video'

    def _format_timestamp(self, seconds: float) -> str:
        total_milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(total_milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        secs, milliseconds = divmod(remainder, 1000)
        return f'{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}'

    def _format_timestamp_for_filename(self, seconds: float) -> str:
        return self._format_timestamp(seconds).replace(':', '-').replace('.', '_')

    def _get_frame_dir(self, video_path: str) -> Path:
        src = Path(video_path).resolve()
        FRAME_DIR.mkdir(parents=True, exist_ok=True)
        frame_dir = FRAME_DIR / self._safe_name(src.stem)
        frame_dir.mkdir(parents=True, exist_ok=True)
        return frame_dir

    def _frame_filename(self, video_path: str, index: int) -> str:
        video_name = self._safe_name(Path(video_path).stem)
        timestamp = self._format_timestamp_for_filename(index * self._time)
        return f'{video_name}_frame_{timestamp}.jpg'

    def _extract_frames(self, video_path: str) -> List[str]:
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            raise RuntimeError('`ffmpeg` not found in PATH.')

        frame_dir = self._get_frame_dir(video_path)
        output_pattern = frame_dir / 'raw_%06d.jpg'
        for existing_path in frame_dir.glob('*.jpg'):
            existing_path.unlink()

        cmd = [
            ffmpeg_path,
            '-y',
            '-i',
            video_path,
            '-vf',
            f'fps=1/{self._time}',
            str(output_pattern),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        raw_frame_paths = sorted(frame_dir.glob('raw_*.jpg'))
        if not raw_frame_paths:
            raise ValueError(f'No frames extracted from video: {video_path}')

        frame_paths = []
        for idx, raw_frame_path in enumerate(raw_frame_paths):
            readable_path = frame_dir / self._frame_filename(video_path, idx)
            if readable_path.exists():
                readable_path.unlink()
            raw_frame_path.rename(readable_path)
            frame_paths.append(str(readable_path))
        return frame_paths

    def _load_data(
        self, file: Path,
        fs: Optional['fsspec.AbstractFileSystem'] = None,
    ) -> List[ImageDocNode]:
        if not isinstance(file, Path):
            file = Path(file)

        fs = fs or get_default_fs()
        if not is_default_fs(fs):
            raise NotImplementedError('VideoFrameReader currently supports local video paths only')

        video_path = os.path.abspath(str(file))
        frame_paths = self._extract_frames(video_path)

        nodes: List[ImageDocNode] = []
        for idx, frame_path in enumerate(frame_paths):
            frame_nodes = self._image_reader._load_data(Path(frame_path), fs=fs)
            frame_time_seconds = idx * self._time
            for node in frame_nodes:
                node.metadata['video_source_path'] = video_path
                node.metadata['frame_path'] = frame_path
                node.metadata['frame_index'] = idx
                node.metadata['frame_interval_seconds'] = self._time
                node.metadata['frame_time_seconds'] = frame_time_seconds
                node.metadata['frame_timestamp'] = self._format_timestamp(frame_time_seconds)
                node.metadata['multimodal_type'] = 'video_audio_frame'
            nodes.extend(frame_nodes)
        return nodes


__all__ = ['VideoFrameReader']
