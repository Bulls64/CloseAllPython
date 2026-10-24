# Contributing

[English](#english) · [Français](#français)

## English

Bug reports and ideas are welcome in the [issues](https://github.com/Bulls64/CloseAllPython/issues);
the forms ask for what is needed (version, Windows version, steps). Security problems go through
[SECURITY.md](SECURITY.md), not a public issue.

To work on the code (Windows 10 or 11, Python 3.14):

```bat
python -m venv .venv
.venv\Scripts\activate
pip install --require-hashes --only-binary=:all: -r requirements.txt
python closeallpython.py
python -m unittest discover -s tests -t .
build.bat
```

- The tests run on any system: `tests/fakewin.py` replaces the Windows calls. The interface test
  (`tests/test_gui_smoke.py`) needs a display; the three tests marked "needs Windows" use the real API.
- Every text shown to the user exists in English and French (`closeall/i18n.py`).
- Add an entry to both parts of `CHANGELOG.md`; the release notes are taken from it.
- Changing a dependency: update its version **and** its hashes in `requirements*.txt`
  (instructions at the top of `requirements.txt`).
- A pull request runs the tests and builds both executables on GitHub.

## Français

Signalements de bugs et idées sont les bienvenus dans les
[issues](https://github.com/Bulls64/CloseAllPython/issues) ; les formulaires demandent ce qu'il faut
(version, version de Windows, étapes). Les problèmes de sécurité passent par
[SECURITY.md](SECURITY.md), pas par un ticket public.

Pour travailler sur le code (Windows 10 ou 11, Python 3.14) : mêmes commandes que ci-dessus.

- Les tests tournent sur tout système : `tests/fakewin.py` remplace les appels Windows. Le test de
  l'interface (`tests/test_gui_smoke.py`) demande un affichage ; les trois tests marqués « needs
  Windows » utilisent la vraie API.
- Tout texte affiché existe en anglais et en français (`closeall/i18n.py`).
- Ajoutez une entrée dans les deux parties de `CHANGELOG.md` ; les notes de release en sont tirées.
- Pour changer une dépendance, mettez à jour sa version **et** ses empreintes dans
  `requirements*.txt` (explications en tête de `requirements.txt`).
- Une pull request lance les tests et compile les deux exécutables sur GitHub.
