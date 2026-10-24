"""Write the GitHub release notes of a version from CHANGELOG.md (English and French entries).

Usage: python .github/scripts/release_notes.py 1.9.4 notes.md [--published tags.txt]

With --published (a file listing the tags already released on GitHub, one per line), the notes
also cover every version since the previous release: a version that never had its own release
(1.8.0, 1.9.3) is not left out of the notes of the next one.
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DOWNLOAD = """### Download

- `CloseAllPython.exe`: graphical application
- `CloseAllPython-CLI.exe`: command line

No installation needed; Windows 10 or 11. The executables are not code-signed: if Windows SmartScreen shows \
"Windows protected your PC", click **More info**, then **Run anyway**. To check a download, compare its \
SHA-256 with the one GitHub shows next to the file."""

DOWNLOAD_FR = """### Téléchargement

- `CloseAllPython.exe` : application graphique
- `CloseAllPython-CLI.exe` : ligne de commande

Aucune installation ; Windows 10 ou 11. Les exécutables ne sont pas signés : si Windows SmartScreen affiche \
« Windows a protégé votre ordinateur », cliquez sur **Informations complémentaires**, puis sur **Exécuter quand même**. \
Pour vérifier un téléchargement, comparez son empreinte SHA-256 à celle que GitHub affiche à côté du fichier."""

HEADING = re.compile(r"^## (\d+(?:\.\d+)*)\b.*?$\n(.*?)(?=^## |^---|^# |\Z)", re.M | re.S)


def parse(version):
    return tuple(int(part) for part in version.removeprefix("v").split("."))


def entries(text):
    """{version: [English body, French body]} from the CHANGELOG, in file order."""
    found = {}
    for version, body in HEADING.findall(text):
        found.setdefault(version, []).append(body.strip())
    return found


def previous_release(version, published):
    """The highest published version below `version`, or None."""
    tags = [parse(tag.strip()) for tag in published if re.fullmatch(r"v?\d+(?:\.\d+)*", tag.strip())]
    older = [tag for tag in tags if tag < parse(version)]
    return max(older) if older else None


def notes(version, published=(), text=None):
    found = entries(text if text is not None else (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    if version not in found:
        raise SystemExit(f"CHANGELOG.md has no entry for {version}")
    since = previous_release(version, published)
    if since is None:   # no list, or the first release: this version only
        covered = [version]
    else:
        covered = sorted((v for v in found if since < parse(v) <= parse(version)), key=parse, reverse=True)
    parts = []
    for index, (title, download) in enumerate((("### Changes", DOWNLOAD), ("### Modifications", DOWNLOAD_FR))):
        bodies = [(v, found[v][index]) for v in covered if len(found[v]) > index]
        if not bodies:
            continue
        if parts:
            parts.append("---")
        parts.append(title)
        if len(bodies) == 1:
            parts.append(bodies[0][1])
        else:
            parts += [f"#### {v}\n\n{body}" for v, body in bodies]
        parts.append(download)
    return "\n\n".join(parts) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("out")
    parser.add_argument("--published", help="file with the tags already released, one per line")
    args = parser.parse_args(argv)
    published = Path(args.published).read_text(encoding="utf-8").split() if args.published else ()
    Path(args.out).write_text(notes(args.version.removeprefix("v"), published), encoding="utf-8")


if __name__ == "__main__":
    main()
