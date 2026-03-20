import os
from typing import Tuple, List, Optional
from lazyllm import LOG


class SensitiveFilter:

    def __init__(self, keyword_path: Optional[str] = None):
        """初始化敏感词过滤器"""
        self.actree = None
        self.loaded = False
        self.keyword_count = 0

        if keyword_path:
            self._load_keywords(keyword_path)

    def _load_keywords(self, path: str):
        """从文件加载敏感词并构建 AC 自动机"""
        try:
            import ahocorasick
        except ImportError:
            LOG.error(
                "[SensitiveFilter] pyahocorasick not installed. "
                "Please install: pip install pyahocorasick"
            )
            return

        if not os.path.exists(path):
            LOG.warning(f"[SensitiveFilter] Keyword file not found: {path}")
            return

        if not os.path.isfile(path):
            LOG.warning(f"[SensitiveFilter] Path is not a file: {path}")
            return

        # 初始化 AC 自动机
        self.actree = ahocorasick.Automaton()

        # 加载敏感词
        loaded_count = 0
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    word = line.strip()
                    if word:  # 跳过空行

                        self.actree.add_word(word, (word, "default"))
                        loaded_count += 1

            # 构建失败指针（这是 AC 自动机的核心）
            self.actree.make_automaton()
            self.loaded = True
            self.keyword_count = loaded_count

        except Exception as e:
            LOG.error(f"[SensitiveFilter] Failed to load keywords: {e}")
            self.actree = None
            self.loaded = False

    def check(self, text: str) -> Tuple[bool, str]:
        """检查文本是否包含敏感词"""
        if not self.loaded or not self.actree:
            return False, ""

        if not text:
            return False, ""

        # AC 自动机匹配
        # iter() 返回 (end_index, (word, category))
        try:
            for end_index, (word, category) in self.actree.iter(text):
                # 只要命中一个敏感词就立即返回
                return True, word
        except Exception as e:
            LOG.error(f"[SensitiveFilter] Error during check: {e}")
            # 发生错误时默认通过（不阻断业务）
            return False, ""

        return False, ""
