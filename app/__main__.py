import atexit
import os
import subprocess
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from .window import MainWindow
from .worker import Worker


def main() -> None:
    env = dict(os.environ)
    if not env.get("ASSISTANT_API_KEY"):
        env["ASSISTANT_API_KEY"] = "dev-key"
    os.environ["ASSISTANT_API_KEY"] = env["ASSISTANT_API_KEY"]
    proc = subprocess.Popen(
        [sys.executable, "-m", "core.api.server"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
    )
    atexit.register(proc.terminate)

    sys.setswitchinterval(0.002)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  
    window = MainWindow(Worker)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
