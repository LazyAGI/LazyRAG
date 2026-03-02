import os
from lazyllm.tools.servers.mineru import MineruServer

if __name__ == "__main__":
    mineru_server = MineruServer(port=int(os.getenv('MINERU_SERVER_PORT', '8000')))
    mineru_server.start()
