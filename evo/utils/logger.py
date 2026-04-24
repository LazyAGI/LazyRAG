import logging
import sys
import os
from datetime import datetime


class Logger:
    _instance = None

    def __new__(cls, log_dir="logs", log_name="eval", level=logging.INFO):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_logger(log_dir, log_name, level)
        return cls._instance

    def _init_logger(self, log_dir, log_name, level):
        # 创建日志目录
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # 日志文件名
        log_file = os.path.join(log_dir, f"{log_name}_{datetime.now().strftime('%Y%m%d')}.log")

        # 日志格式
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(filename)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # 配置 logger
        self.logger = logging.getLogger(log_name)
        self.logger.setLevel(level)
        self.logger.handlers.clear()  # 避免重复添加 handler

        # 文件输出
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # 控制台输出
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def debug(self, msg):
        self.logger.debug(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def critical(self, msg):
        self.logger.critical(msg)


log = Logger()
