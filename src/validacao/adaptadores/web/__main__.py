"""`validacao-painel` → sobe o Streamlit apontando para o app empacotado."""
import sys
from pathlib import Path


def main() -> None:
    from streamlit.web import cli
    app = Path(__file__).with_name("painel_app.py")
    sys.argv = ["streamlit", "run", str(app), "--server.address=0.0.0.0", "--server.port=8501",
                "--server.headless=true", "--browser.gatherUsageStats=false"]
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
