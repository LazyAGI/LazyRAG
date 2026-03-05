import os

from lazyllm.tools.servers.mineru.mineru_server_module import MineruServer

if __name__ == '__main__':
    MineruServer(port=int(os.getenv('LAZYRAG_MINERU_SERVER_PORT', '8000'))).start()
