from pathlib import Path
import tempfile
from typing import List, Optional

from lazyllm.thirdparty import fsspec
from lazyllm.tools.rag.doc_node import DocNode
from lazyllm.tools.rag.readers.readerBase import LazyLLMReaderBase

from config import config as _cfg


class VideoAudioReader(LazyLLMReaderBase):
    __lazyllm_registry_disable__ = True

    def __init__(
        self, model_version: Optional[str] = None, return_trace: bool = True,
        time_segment: bool = False, time_interval: Optional[int] = None,
    ) -> None:
        super().__init__(return_trace=return_trace)
        self._model_version = model_version or _cfg['whisper_model']
        self._time_segment = time_segment
        self._time_interval = time_interval if time_interval is not None else _cfg['audio_segment_interval']
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                import whisper
            except ImportError as exc:
                raise ImportError(
                    'Please install OpenAI whisper model `pip install openai-whisper` to use the model'
                ) from exc
            self._model = whisper.load_model(self._model_version)
        return self._model

    def __getstate__(self):
        state = self.__dict__.copy()
        state['_model'] = None
        return state

    def _load_data(
        self, file: Path,
        fs: Optional['fsspec.AbstractFileSystem'] = None
    ) -> List[DocNode]:
        if not isinstance(file, Path):
            file = Path(file)

        video_input = False
        video_file_path = None
        temp_audio_file = None
        if file.suffix.lower() == '.mp4':
            try:
                from pydub import AudioSegment
            except ImportError as exc:
                raise ImportError('Please install pydub `pip install pydub`') from exc

            if fs:
                with fs.open(file, 'rb') as f:
                    video = AudioSegment.from_file(f, format='mp4')
            else:
                video = AudioSegment.from_file(file, format='mp4')

            video_input = True
            audio = video
            video_file_path = file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_file:
                temp_audio_file = Path(tmp_file.name)
            file = temp_audio_file
            audio.export(str(file), format='mp3')

        model = self._get_model()
        metadata_audio_path = video_file_path if video_input and video_file_path is not None else file

        try:
            if self._time_segment:
                result = model.transcribe(str(file), word_timestamps=True)
                return self._merge_segments(result['segments'], metadata_audio_path, video_input, video_file_path)

            result = model.transcribe(str(file))
            transcript = result['text']
            metadata = {
                'start_time': 0,
                'end_time': float('inf'),
                'audio_file_path': str(metadata_audio_path),
                'multimodal_type': 'video_audio_text',
            }
            if video_input:
                metadata['video_file_path'] = str(video_file_path)
            return [DocNode(text=transcript, metadata=metadata)]
        finally:
            if temp_audio_file is not None:
                temp_audio_file.unlink(missing_ok=True)

    def _merge_segments(
        self, segments, metadata_audio_path: Path, video_input: bool = False,
        video_file_path: Optional[Path] = None,
    ) -> List[DocNode]:
        nodes = []
        merged_text = []
        merged_start = None
        merged_end = None

        def _build_node(start_time, end_time, texts):
            metadata = {
                'start_time': start_time,
                'end_time': end_time,
                'audio_file_path': str(metadata_audio_path),
                'multimodal_type': 'video_audio_text',
            }
            if video_input and video_file_path is not None:
                metadata['video_file_path'] = str(video_file_path)
            return DocNode(text=''.join(texts), metadata=metadata)

        for segment in segments:
            start_time = segment['start']
            end_time = segment['end']
            text = segment['text']

            if merged_start is None:
                merged_start = start_time
                merged_end = end_time
                merged_text.append(text)
                continue

            if end_time - merged_start < self._time_interval:
                merged_end = end_time
                merged_text.append(text)
                continue

            nodes.append(_build_node(merged_start, merged_end, merged_text))
            merged_start = start_time
            merged_end = end_time
            merged_text = [text]

        if merged_start is not None:
            nodes.append(_build_node(merged_start, merged_end, merged_text))

        return nodes


__all__ = ['VideoAudioReader']
