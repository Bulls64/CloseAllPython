"""Write the GitHub release notes of a version from CHANGELOG.md (English and French entries).

Usage: python .github/scripts/release_notes.py 1.5.1 notes.md
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DOWNLOAD = """### Download

- `CloseAllPython.exe`: graphical application
- `CloseAllPython-CLI.exe`: command line

No installation needed; Windows 10 or 11. The executables are not code-signed: if Windows SmartScreen shows \
"Windows protected your PC", click **More info**, then **Run anyway**."""

DOWNLOAD_FR = """### Téléchargement

- `CloseAllPython.exe` : application graphique
- `CloseAllPython-CLI.exe` : ligne de commande

Aucune installation ; Windows 10 ou 11. Les exécutables ne sont pas signés : si Windows SmartScreen affiche \
« Windows a protégé votre ordinateur », cliquez sur **Informations complémentaires**, puis sur **Exécuter quand même**."""


def sections(text, version):
    """Bodies of every '## <version> (...)' section, in file order (English first, then French)."""
    pattern = re.compile(rf"^## {re.escape(version)}\b.*?$\n(.*?)(?=^## |^---|^# |\Z)", re.M | re.S)
    return [body.strip() for body in pattern.findall(text)]


def notes(version):
    found = sections((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    if not found:
        raise SystemExit(f"CHANGELOG.md has no entry for {version}")
    english = found[0]
    french = found[1] if len(found) > 1 else ""
    parts = ["### Changes", english, DOWNLOAD]
    if french:
        parts += ["---", "### Modifications", french, DOWNLOAD_FR]
    return "\n\n".join(parts) + "\n"


if __name__ == "__main__":
    version, out = sys.argv[1].removeprefix("v"), sys.argv[2]
    Path(out).write_text(notes(version), encoding="utf-8")
