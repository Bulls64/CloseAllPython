# Security policy

[English](#english) · [Français](#français)

## English

### Supported versions

Only the latest release receives fixes. The built-in updater (Settings › About) installs it.

### Reporting a vulnerability

Please do not open a public issue. Use **Security › Report a vulnerability** on this repository
(a private GitHub advisory), or the address shown on the [Bulls64](https://github.com/Bulls64) profile.
Say which version you use, what an attacker can do and how to reproduce it. You will get an answer
within a week; the fix is published in a new release whose notes credit you if you wish.

### What protects you today

- The executables are built and tested by GitHub Actions from the tagged code; a release only
  publishes those exact files.
- The updater downloads only from `https://github.com/Bulls64/CloseAllPython/releases/download/…`
  and checks the SHA-256 that GitHub publishes for the file before replacing anything.
- Build dependencies are pinned by SHA-256 and the GitHub actions by commit.
- The executables are **not code-signed**. To check a download by hand, compare
  `Get-FileHash CloseAllPython.exe` (PowerShell) with the SHA-256 shown next to the file on the
  release page.

### Limits to know

- The updater trusts GitHub: someone who took over the maintainer's account could publish a
  harmful version. Automatic updates are off by default.
- "Restart as administrator" runs the program from the folder it is in. Keep it in
  `C:\Program Files\CloseAllPython` if you use administrator mode regularly; the application
  warns you otherwise.
- Window titles are written to the log only if you turn this on (Settings › About).

## Français

### Versions suivies

Seule la dernière release reçoit des correctifs. La mise à jour intégrée (Paramètres › À propos)
l'installe.

### Signaler une faille

N'ouvrez pas de ticket public. Utilisez **Security › Report a vulnerability** sur ce dépôt (avis
privé GitHub), ou l'adresse indiquée sur le profil [Bulls64](https://github.com/Bulls64). Indiquez la
version utilisée, ce qu'un attaquant peut faire et comment le reproduire. Vous aurez une réponse sous
une semaine ; le correctif sort dans une nouvelle release, dont les notes vous citent si vous le
souhaitez.

### Ce qui vous protège aujourd'hui

- Les exécutables sont compilés et testés par GitHub Actions à partir du code tagué ; une release
  publie exactement ces fichiers.
- La mise à jour ne télécharge que depuis
  `https://github.com/Bulls64/CloseAllPython/releases/download/…` et vérifie l'empreinte SHA-256
  publiée par GitHub avant de remplacer quoi que ce soit.
- Les dépendances de compilation sont figées par empreinte SHA-256, les actions GitHub par commit.
- Les exécutables **ne sont pas signés**. Pour vérifier un téléchargement à la main, comparez
  `Get-FileHash CloseAllPython.exe` (PowerShell) avec l'empreinte SHA-256 affichée à côté du
  fichier sur la page de la release.

### Limites à connaître

- La mise à jour fait confiance à GitHub : quelqu'un qui prendrait le contrôle du compte du
  mainteneur pourrait publier une version malveillante. La mise à jour automatique est désactivée
  par défaut.
- « Redémarrer en administrateur » lance le programme depuis son dossier. Placez-le dans
  `C:\Program Files\CloseAllPython` si vous utilisez souvent le mode administrateur ; sinon
  l'application vous prévient.
- Les titres des fenêtres ne sont écrits dans le journal que si vous l'activez (Paramètres › À propos).
