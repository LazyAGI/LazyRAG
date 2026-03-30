import os

from lazyllm.tools.servers.mineru.mineru_server_module import MineruServer

if __name__ == '__main__':
    server = MineruServer(
        port=int(os.getenv('LAZYRAG_MINERU_SERVER_PORT', '8000')),
        default_backend=os.getenv('LAZYRAG_MINERU_BACKEND', 'pipeline'),
        cache_dir=os.getenv('LAZYRAG_MINERU_CACHE_DIR'),
        image_save_dir=os.getenv('LAZYRAG_MINERU_IMAGE_SAVE_DIR'),
    )
    server.start()
    server.wait()
