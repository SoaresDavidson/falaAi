import argparse
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="falaai")
    sub = parser.add_subparsers(dest="comando", required=True)

    auth = sub.add_parser("auth", help="autoriza o acesso ao Gmail e grava o token")
    auth.add_argument("--client-secret", type=Path, required=True)
    auth.add_argument("--saida", type=Path, required=True)

    serve = sub.add_parser("serve", help="sobe o app do servidor")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

    tts = sub.add_parser("tts-serve", help="sobe o serviço Kokoro do laptop")
    tts.add_argument("--host", default="127.0.0.1")
    tts.add_argument("--port", type=int, default=8880)

    args = parser.parse_args(argv)

    if args.comando == "auth":
        from falaai.gmail import autorizar

        autorizar(args.client_secret, args.saida)
    else:
        import uvicorn

        alvo = (
            "falaai.app:criar_app"
            if args.comando == "serve"
            else "falaai.tts_service.app:criar_app"
        )
        uvicorn.run(alvo, factory=True, host=args.host, port=args.port)
    return 0
