"""Выполняет ноутбук через текущий Python без установки kernelspec в профиль пользователя."""
import json
from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient
from jupyter_client.kernelspec import KernelSpecManager

ROOT = Path(__file__).resolve().parents[1]


class LocalKernelSpecManager(KernelSpecManager):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kernel_dirs = [str(ROOT / "runtime" / "kernels")]


if __name__ == "__main__":
    directory = ROOT / "runtime" / "kernels" / "blini-local"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "kernel.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Blini local", "language": "python"}), encoding="utf-8")
    notebook = nbformat.read(ROOT / "notebooks" / "analysis.ipynb", as_version=4)
    client = NotebookClient(notebook, timeout=120, kernel_name="blini-local", allow_errors=False,
                            resources={"metadata": {"path": str(ROOT)}},
                            kernel_manager_class="jupyter_client.manager.KernelManager")
    manager = client.create_kernel_manager()
    manager.kernel_spec_manager = LocalKernelSpecManager()
    client.km = manager
    client.execute()
    target = ROOT / "notebooks" / "analysis.executed.ipynb"
    nbformat.write(notebook, target)
    print(f"Notebook OK: {sum(c.cell_type == 'code' for c in notebook.cells)} code cells; {target}")
