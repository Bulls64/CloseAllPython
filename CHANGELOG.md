# Changelog

## 1.6.0 (2026-10-16)

Updates from GitHub
- New "Check for updates" button in Settings › About: reads the latest release of the GitHub repository and, when it is newer, offers to install it and restart.
- New setting "Update automatically at startup" (off by default): checks GitHub two seconds after the window opens, installs a newer version in the background and offers to restart; otherwise the new version is used at the next start.
- New CLI option `--update`: installs the latest release over the running executable (`CloseAllPython-CLI.exe --update`).
- The downloaded executable must match the size and the SHA-256 checksum published by GitHub for the release and start like a Windows program, otherwise nothing is replaced. The running file is renamed (`.old`), the new one takes its place, and the old copy is removed at the next start; if the swap fails, the previous version is put back.
- Running from source, the application only reports a new version and points to `git pull` or the release page.
- The application contacts GitHub only when you check for updates or when the automatic update is on.

## 1.5.1 (2026-10-16)

- Sharp application icon in the title bar, the taskbar and Alt+Tab on scaled displays (125 %, 150 %, 200 %...). Tk's `wm iconbitmap` always used the 16 and 32 px images of the icon, which Windows then enlarged; the window now gets icons at the exact size of its monitor's scaling (designed image when the .ico has that size, otherwise reduced from a larger one), updated when the window moves to a monitor with another scaling. Dialogs too.
- Bottom bar of the application list: the buttons keep their full width ("Close Explorer windows" was cut off in French when applications were selected) and the texts on the left wrap instead.
- README rewritten for GitHub, with screenshots in `docs/screenshots`.
- Released under the MIT License (`LICENSE` file); the copyright notice is also shown in the properties of the executables.
- README: note about the Windows SmartScreen / antivirus warning on the unsigned executables.
- GitHub Actions: tests on Windows with Python 3.14 on every push; a version tag builds both executables and attaches them to its release, with notes taken from this changelog.

## 1.5.0 (2026-10-16)

Automatic refresh, performance and error-reporting improvements.

Automatic refresh
- The list of open windows refreshes by itself after applications are closed: at once, then after 0.4 s, 1.2 s and 3 s for windows that disappear late (UWP frames, slow applications). No need to press "Done" or F5.
- "Close Explorer windows" refreshes the list after 0.7 s and again after 2 s; its message stays in the status bar for 4 s.
- Automatic refreshes wait while a dialog is open, so a confirmation never disagrees with the list behind it.
- Closed applications leave the selection.

Performance
- Instant force-stop terminates every selected application first, then waits for all of them against one shared 3 s deadline (previously up to 3 s per application, one after the other). Survivors of a normal close are force-stopped the same way.
- Normal close: the program sleeps on a survivor's process handle and wakes the moment it exits, instead of checking every 100 ms.
- Icons are extracted on a background thread and preloaded after each refresh: the window no longer waits for them (with slow icons: 0.5 s instead of 1.6 s in the test).
- A refresh keeps the cards whose content did not change instead of rebuilding the whole list; counters are computed once per refresh.
- Window titles read with `InternalGetWindowText`: one call, and no message sent to the window, so a frozen application cannot stall the list. Executable paths use a small buffer first.

Visible errors
- A failure at startup is no longer silent in the windowed executable: message box with the reason, details in `%APPDATA%\CloseAllPython\crash.txt`. A missing pywin32 is reported the same way.
- An error in an interface action opens an "Unexpected error" dialog and is saved to `crash.txt` and the log.

## 1.4.0 (2026-10-15)

- New "Close Explorer windows" button and `--close-explorer` CLI option: closes only the File Explorer folder windows (all tabs); `explorer.exe`, the desktop and the taskbar keep running.

## 1.3.0 (2026-10-15)

- Selected applications are now force-stopped immediately: no `WM_CLOSE` phase, no waiting delay. Protected shell processes and PID verification are unchanged.
- New setting "Force-stop instantly" (on by default); turn it off to get the previous close-then-offer-force flow.
- CLI: immediate force-stop by default; `--graceful` restores the polite close with `--timeout`. `--force` is kept for compatibility.

## 1.2.0 (2026-10-15)

- New CustomTkinter interface: navigation rail, application cards with icons and product names, search and selection filter, protected processes listed apart.
- Live closing screen: per-application status, progress, "Show window", "Leave open" and force-stop of the survivors.
- Log screen reading the action log; settings screen saved automatically.
- Theme setting: system, light or dark (replaces the dark-mode switch; old settings are migrated).
- Proper singular/plural forms in both languages.

## 1.1.0 (2026-10-15)

Safety
- Applications are asked to close (`WM_CLOSE`) before any force-stop; force-stop needs a confirmation (GUI) or `--force` (CLI), and uses exit code 1.
- Protected shell processes (Explorer, ApplicationFrameHost, TextInputHost…) can never be closed.
- UWP apps are resolved to their real process instead of ApplicationFrameHost.
- PID reuse detected through the process creation time; window handles re-read just before closing.
- CLI: `--no-ui` requires `--close TEXT` (non-empty) or an explicit `--all`; confirmation unless `--yes`; `--dry-run`; never closes its own terminal or parent processes.
- Window icons are queried with `SendMessageTimeout`: a hung application no longer freezes the GUI.

Fixes
- Hidden "cloaked" and tool windows are no longer listed.
- Ticked windows stay ticked while searching; search is debounced; icons are cached.
- Process names and icons work for elevated processes (`PROCESS_QUERY_LIMITED_INFORMATION`).
- "Restart as administrator" button; access-denied errors explain what to do.
- Long confirmation lists are truncated.
- Icons keep their transparency; DPI awareness and scaled layout on high-DPI screens.
- Theme: muted labels keep their colour, visible text cursor in dark mode, themed scrollbar and settings controls.
- All messages translated (GUI and CLI); mouse wheel only scrolls the list under the pointer.
- Settings: strict validation (`"false"` is no longer read as true), atomic save.

Project
- Code split into the `closeall` package; unit tests (`tests/`).
- `build.bat` uses a private venv, pinned dependencies, runs the tests and builds from the `.spec` files.
- UPX disabled, version resource embedded in the executables, optional code signing.
- Action log in `%APPDATA%\CloseAllPython\closeallpython.log`; `.gitignore` for generated files.

---

# Journal des modifications (version française)

## 1.6.0 (2026-10-16)

Mises à jour depuis GitHub
- Nouveau bouton « Rechercher des mises à jour » dans Paramètres › À propos : lit la dernière release du dépôt GitHub et, si elle est plus récente, propose de l’installer et de redémarrer.
- Nouveau paramètre « Mettre à jour automatiquement au démarrage » (désactivé par défaut) : vérifie GitHub deux secondes après l’ouverture de la fenêtre, installe la nouvelle version en arrière-plan et propose de redémarrer ; sinon, elle est utilisée au prochain démarrage.
- Nouvelle option CLI `--update` : installe la dernière release à la place de l’exécutable en cours (`CloseAllPython-CLI.exe --update`).
- L’exécutable téléchargé doit correspondre à la taille et à l’empreinte SHA-256 publiées par GitHub pour la release, et commencer comme un programme Windows ; sinon rien n’est remplacé. Le fichier en cours est renommé (`.old`), le nouveau prend sa place, et l’ancienne copie est supprimée au démarrage suivant ; si l’échange échoue, la version précédente est remise en place.
- Lancée depuis les sources, l’application signale seulement la nouvelle version et renvoie vers `git pull` ou la page de la release.
- L’application ne contacte GitHub que lorsque vous recherchez des mises à jour ou que la mise à jour automatique est activée.

## 1.5.1 (2026-10-16)

- Icône de l'application nette dans la barre de titre, la barre des tâches et Alt+Tab sur les écrans mis à l'échelle (125 %, 150 %, 200 %...). `wm iconbitmap` de Tk n'utilisait que les images 16 et 32 px de l'icône, que Windows agrandissait ensuite ; la fenêtre reçoit désormais des icônes à la taille exacte de la mise à l'échelle de son écran (image dessinée quand le .ico contient cette taille, sinon réduite à partir d'une plus grande), mises à jour quand la fenêtre passe sur un écran avec une autre échelle. Les boîtes de dialogue aussi.
- Barre du bas de la liste des applications : les boutons gardent toute leur largeur (« Fermer les fenêtres de l'Explorateur » était coupé en français quand des applications étaient sélectionnées) et les textes de gauche passent à la ligne à la place.
- README réécrit pour GitHub, avec des captures d'écran dans `docs/screenshots`.
- Publié sous licence MIT (fichier `LICENSE`) ; la mention de copyright apparaît aussi dans les propriétés des exécutables.
- README : note sur l'avertissement Windows SmartScreen / antivirus pour les exécutables non signés.
- GitHub Actions : tests sous Windows avec Python 3.14 à chaque push ; un tag de version compile les deux exécutables et les joint à sa release, avec des notes tirées de ce journal.

## 1.5.0 (2026-10-16)

Améliorations : actualisation automatique, performances et signalement des erreurs.

Actualisation automatique
- La liste des fenêtres ouvertes s'actualise toute seule après la fermeture d'applications : immédiatement, puis après 0,4 s, 1,2 s et 3 s pour les fenêtres qui disparaissent tardivement (cadres UWP, applications lentes). Plus besoin d'appuyer sur « Terminé » ou F5.
- « Fermer les fenêtres de l'Explorateur » actualise la liste après 0,7 s puis de nouveau après 2 s ; son message reste affiché dans la barre d'état pendant 4 s.
- Les actualisations automatiques attendent tant qu'une boîte de dialogue est ouverte, pour qu'une confirmation ne contredise jamais la liste située derrière.
- Les applications fermées sortent de la sélection.

Performances
- L'arrêt forcé immédiat termine d'abord toutes les applications sélectionnées, puis attend l'ensemble avec une échéance commune de 3 s (auparavant jusqu'à 3 s par application, l'une après l'autre). Les survivantes d'une fermeture normale sont arrêtées de la même façon.
- Fermeture normale : le programme attend sur le handle du processus d'une survivante et se réveille dès qu'elle se termine, au lieu de vérifier toutes les 100 ms.
- Les icônes sont extraites dans un thread d'arrière-plan et préchargées après chaque actualisation : la fenêtre ne les attend plus (avec des icônes lentes : 0,5 s au lieu de 1,6 s lors du test).
- Une actualisation conserve les cartes dont le contenu n'a pas changé au lieu de reconstruire toute la liste ; les compteurs sont calculés une seule fois par actualisation.
- Titres de fenêtres lus avec `InternalGetWindowText` : un seul appel et aucun message envoyé à la fenêtre, donc une application figée ne peut plus bloquer la liste. Les chemins d'exécutables utilisent d'abord un petit tampon.

Erreurs visibles
- Un échec au démarrage n'est plus silencieux dans l'exécutable sans console : boîte de message avec la raison, détails dans `%APPDATA%\CloseAllPython\crash.txt`. L'absence de pywin32 est signalée de la même manière.
- Une erreur dans une action de l'interface ouvre une boîte « Erreur inattendue » et est enregistrée dans `crash.txt` et dans le journal.

## 1.4.0 (2026-10-15)

- Nouveau bouton « Fermer les fenêtres de l'Explorateur » et option CLI `--close-explorer` : ferme uniquement les fenêtres de dossiers de l'Explorateur de fichiers (tous les onglets) ; `explorer.exe`, le bureau et la barre des tâches continuent de fonctionner.

## 1.3.0 (2026-10-15)

- Les applications sélectionnées sont maintenant arrêtées de force immédiatement : pas de phase `WM_CLOSE`, pas de délai d'attente. Les processus protégés du shell et la vérification du PID restent inchangés.
- Nouveau paramètre « Arrêt forcé immédiat » (activé par défaut) ; le désactiver rétablit l'ancien fonctionnement : fermeture puis proposition d'arrêt forcé.
- CLI : arrêt forcé immédiat par défaut ; `--graceful` rétablit la fermeture normale avec `--timeout`. `--force` est conservé pour la compatibilité.

## 1.2.0 (2026-10-15)

- Nouvelle interface CustomTkinter : barre de navigation, cartes d'applications avec icônes et noms de produit, recherche et filtre de sélection, processus protégés listés à part.
- Écran de fermeture en direct : état par application, progression, « Afficher la fenêtre », « Laisser ouvert » et arrêt forcé des survivantes.
- Écran Journal lisant le journal des actions ; écran Paramètres enregistré automatiquement.
- Paramètre de thème : système, clair ou sombre (remplace l'interrupteur du mode sombre ; les anciens paramètres sont migrés).
- Singulier et pluriel corrects dans les deux langues.

## 1.1.0 (2026-10-15)

Sécurité
- Les applications reçoivent d'abord une demande de fermeture (`WM_CLOSE`) avant tout arrêt forcé ; l'arrêt forcé exige une confirmation (interface) ou `--force` (CLI) et utilise le code de sortie 1.
- Les processus protégés du shell (Explorer, ApplicationFrameHost, TextInputHost…) ne peuvent jamais être fermés.
- Les applications UWP sont résolues vers leur vrai processus au lieu d'ApplicationFrameHost.
- Réutilisation de PID détectée grâce à l'heure de création du processus ; handles de fenêtres relus juste avant la fermeture.
- CLI : `--no-ui` exige `--close TEXTE` (non vide) ou un `--all` explicite ; confirmation sauf avec `--yes` ; `--dry-run` ; ne ferme jamais son propre terminal ni ses processus parents.
- Les icônes de fenêtres sont demandées avec `SendMessageTimeout` : une application bloquée ne fige plus l'interface.

Corrections
- Les fenêtres masquées (« cloaked ») et les fenêtres d'outils ne sont plus listées.
- Les fenêtres cochées restent cochées pendant la recherche ; la recherche est temporisée ; les icônes sont mises en cache.
- Les noms de processus et les icônes fonctionnent pour les processus élevés (`PROCESS_QUERY_LIMITED_INFORMATION`).
- Bouton « Redémarrer en administrateur » ; les erreurs d'accès refusé expliquent quoi faire.
- Les longues listes de confirmation sont tronquées.
- Les icônes conservent leur transparence ; prise en charge du DPI et mise en page adaptée aux écrans haute densité.
- Thème : les libellés atténués gardent leur couleur, curseur de texte visible en mode sombre, barre de défilement et contrôles des paramètres thématisés.
- Tous les messages sont traduits (interface et CLI) ; la molette ne fait défiler que la liste sous le pointeur.
- Paramètres : validation stricte (`"false"` n'est plus lu comme vrai), enregistrement atomique.

Projet
- Code découpé dans le paquet `closeall` ; tests unitaires (`tests/`).
- `build.bat` utilise un venv privé, des dépendances figées, lance les tests et compile à partir des fichiers `.spec`.
- UPX désactivé, ressource de version intégrée aux exécutables, signature de code facultative.
- Journal des actions dans `%APPDATA%\CloseAllPython\closeallpython.log` ; `.gitignore` pour les fichiers générés.
