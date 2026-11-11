"""Standard-library installer copied into the local installation bundle."""

import argparse
import hashlib
import os
import shlex
import subprocess
import sys
import venv
from pathlib import Path


def verify(bundle: Path) -> Path:
    manifest = bundle / "SHA256SUMS"
    if not manifest.is_file() or manifest.is_symlink():
        raise ValueError("SHA256SUMS ausente. Execute o instalador dentro do pacote extraído.")
    entries: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, separator, name = line.partition("  ")
        relative = Path(name)
        if (
            not separator
            or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)
            or not name
            or relative.is_absolute()
            or ".." in relative.parts
            or name in entries
        ):
            raise ValueError("Formato inválido em SHA256SUMS")
        path = bundle / relative
        if (
            not path.resolve().is_relative_to(bundle)
            or not path.is_file()
            or any(parent.is_symlink() for parent in [path, *path.parents] if parent != bundle)
        ):
            raise ValueError(f"Arquivo ausente ou caminho inválido: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Integridade inválida: {name}. Extraia novamente o pacote original.")
        entries.add(name)
    wheels = [name for name in entries if name.startswith("backloger-") and name.endswith(".whl")]
    if len(wheels) != 1 or Path(wheels[0]).name != wheels[0] or "install.py" not in entries:
        raise ValueError("Pacote precisa conter um único wheel Backloger e seu instalador")
    return bundle / wheels[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Instalar o pacote local do Backloger em um venv.")
    parser.add_argument(
        "--venv", type=Path, help="Destino; padrão: .venv dentro do pacote extraído."
    )
    parser.add_argument(
        "--wheelhouse", type=Path, help="Dependências locais; desabilita acesso ao índice."
    )
    parser.add_argument("--check", action="store_true", help="Conferir integridade sem instalar.")
    args = parser.parse_args()
    bundle = Path(__file__).resolve().parent
    try:
        if sys.version_info < (3, 12):  # noqa: UP036 - bootstrap also runs on older Python
            raise ValueError("Python 3.12 ou mais recente é necessário")
        wheel = verify(bundle)
        print(f"Integridade verificada: {wheel.name}", flush=True)
        if args.check:
            return
        target = (args.venv or bundle / ".venv").expanduser().absolute()
        if target.is_symlink():
            raise ValueError("O destino do ambiente virtual não pode ser um link simbólico")
        if (
            target.exists()
            and (not target.is_dir() or any(target.iterdir()))
            and not (target / "pyvenv.cfg").is_file()
        ):
            raise ValueError("Destino já contém arquivos e não é um ambiente virtual")
        wheelhouse = args.wheelhouse.expanduser().resolve() if args.wheelhouse else None
        if wheelhouse and not wheelhouse.is_dir():
            raise ValueError("Diretório de dependências locais não existe")
        venv.EnvBuilder(with_pip=True).create(target)
        python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        command = [str(python), "-m", "pip", "install", "--upgrade", "--force-reinstall"]
        if wheelhouse:
            command.extend(["--no-index", "--find-links", str(wheelhouse)])
        subprocess.run([*command, str(wheel)], check=True)
        subprocess.run([str(python), "-m", "pip", "check"], check=True)
        executable = target / ("Scripts/backloger.exe" if os.name == "nt" else "bin/backloger")
        subprocess.run([str(executable), "--version"], check=True)
        print("\nInstalação concluída. Execute:")
        print(shlex.join([str(executable), "--project", "/caminho/do/projeto", "doctor"]))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Erro de instalação: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
