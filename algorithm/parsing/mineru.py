import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lazyllm.tools.servers.mineru.mineru_server_module import MineruServer  # noqa: E402

if __name__ == '__main__':
    MineruServer(port=int(os.getenv('MINERU_SERVER_PORT', '8000'))).start()
