from __future__ import annotations

from chat.app.api import create_app

app = create_app()

if __name__ == '__main__':
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument('--host', type=str, default='0.0.0.0', help='listen host')
    parser.add_argument('--port', type=int, default=8046, help='listen port')
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port)
