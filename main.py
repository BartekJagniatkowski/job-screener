def main():
    """
    Punkt wejścia dla uruchamiania z konsoli.
    
    Użycie:
        python main.py --port 5000
        python main.py --host 0.0.0.0
    """
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Job Screener")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--debug", action="store_true")
    
    args = parser.parse_args()
    
    from app import app, init_db
    init_db()
    
    print(f"Starting on {args.host}:{args.port} (debug={args.debug})")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
