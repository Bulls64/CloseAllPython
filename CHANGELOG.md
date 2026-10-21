# Changelog

## 1.9.3 (2026-10-21)

Security fixes from the code review
- Restart File Explorer, administrator mode: the application no longer starts explorer.exe itself when it runs as administrator. File Explorer would have inherited those rights, and so would every program started afterwards from the taskbar or the Start menu, without a UAC prompt. Windows restarts it with your normal rights (the application waits up to 20 seconds); otherwise a message explains how to start it without administrator rights.
- Updates: the download and release-page addresses read from GitHub are accepted only when they point to this repository on github.com, with a clean path (no "..", encoded characters, user name, port or query). Before, ".../releases/download/../../other/repo/..." passed the check, and the release page was opened as given, which on Windows can start a local or network program.
- explorer.exe is started from the Windows folder reported by Windows, not from the SystemRoot environment variable.
- Build: every Python package (dependencies included) is pinned with the SHA-256 of its files and installed from wheels only, in GitHub Actions and in build.bat; the GitHub actions are pinned to a commit instead of a movable tag.

## 1.9.2 (2026-10-20)

Code clean-up (no change in what the application does)
- Removed dead code: Windows functions nothing called any more (DPI awareness, window check, window icon reading and its timed message), an unused force-stop helper, the duplicate shortcut lookup, an unused list field and button flag, and two texts left over from the former Explorer buttons.
- Shared code instead of copies: one definition of what windows and close targets have in common, one switch style, one page header, one scrolling list, one bitmap header for icons, one decimal-mark rule for numbers, the boolean settings derived from the defaults.
- The Background screen reads the processes on a worker thread, so the window stays responsive while it opens every process; the current list stays visible until the new one is ready.
- Restarting File Explorer reads the Windows session once instead of at every check.

## 1.9.1 (2026-10-20)

Fixes from the review of 1.9.0
- "Close everything" shortcut: when some windows cannot be closed (applications started as administrator, for example), a message now says which ones. The shortcut runs without any window, so a failure used to go unnoticed; the details are still in the log.
- "Close everything" shortcut and `--no-ui --all`: CloseAllPython itself is no longer closed, so the shortcut does not close the window of the application you have open. `--close` can still target it by its title.
- Settings › Shortcut: the shortcut is found whatever the language it was created in ("Close everything" or "Tout fermer"); *Create the shortcut* updates it instead of adding a second one, and *Pin to the taskbar…* is available after a change of language.
- Background screen: a windowless process is no longer hidden because another process of the same executable has a window (a Python service while a Python program is open, for example). Helper processes are now recognised by the application that started them; Windows processes such as Explorer are never treated as that application.
- Background screen: correct wording with a single process ("The one using the most memory").
- GitHub Actions: the executables are built and started on every push (`--self-test`: every module, the window list, process memory, sessions and the COM object of the shortcut, plus `--version` and `--no-ui --all --dry-run`), and a release publishes exactly those tested files.

## 1.9.0 (2026-10-20)

Restart File Explorer
- New **Restart** button in the bottom bar of the application list, next to the button that closes File Explorer windows; both now sit together under a "File Explorer" caption with shorter labels, so the bar keeps room at small window sizes.
- After a confirmation, every explorer.exe of your Windows session is stopped (other users' sessions are not touched). Windows restarts the shell by itself, as your own process; if it has not done so after 8 seconds, the application starts explorer.exe. The taskbar and desktop disappear for a few seconds and File Explorer windows are closed; other applications keep running.
- The status bar shows the progress and the result; the list refreshes afterwards. The restart is written to the log.

## 1.8.0 (2026-10-19)

Background processes
- New **Background** screen (in the left bar): the 10 processes without any window that use the most memory, largest first, with their icon, name, PID, memory and a bar to compare them. The summary gives how many background processes run and how much memory they use in all.
- Memory is the private working set, the "Memory" column of the Task Manager. It is read in one system call that needs no access to the processes, so services and protected processes are measured too, without administrator rights.
- Helper processes of an application that has a window stay with that application (a browser's or Steam's helpers are not listed while its window is open).
- Windows processes (Memory Compression, Explorer, svchost...) are left out by default; the *Include Windows processes* switch shows them, greyed and tagged "Windows". The choice is saved.
- The list is read each time the screen opens and with *Refresh*. It only lists: nothing is closed from this screen.

## 1.7.0 (2026-10-17)

"Close everything" shortcut
- New **Shortcut** section in Settings: *Create the shortcut* puts a "Close everything" shortcut on the desktop. Running it starts the application without any window (`--no-ui --all -y`) and instantly force-closes every open window, with no confirmation; protected Windows processes are still skipped. Unsaved work is lost, as the section says.
- *Pin to the taskbar…* shows the shortcut in File Explorer with the steps to pin it: right-click › "Pin to taskbar" (Windows 11: "Show more options" first), or drag it onto the taskbar. Windows gives programs no way to pin themselves, so this last click stays yours.
- The shortcut points to the application where it is installed: updates replace the file in place, so it keeps working. If you move the application, create the shortcut again.
- From source, the shortcut runs `pythonw.exe closeallpython.py` with the same options.

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

## 1.9.3 (2026-10-21)

Corrections de sécurité issues de la revue du code
- Redémarrer l'Explorateur en mode administrateur : l'application ne lance plus explorer.exe elle-même quand elle tourne en administrateur. L'Explorateur aurait hérité de ces droits, comme tout programme lancé ensuite depuis la barre des tâches ou le menu Démarrer, sans demande UAC. Windows le relance avec vos droits normaux (l'application attend jusqu'à 20 secondes) ; sinon un message explique comment le relancer sans droits administrateur.
- Mises à jour : les adresses de téléchargement et de page de release lues sur GitHub ne sont acceptées que si elles désignent ce dépôt sur github.com, avec un chemin propre (pas de « .. », de caractères encodés, de nom d'utilisateur, de port ni de paramètres). Avant, « …/releases/download/../../autre/depot/… » passait le contrôle, et la page de release était ouverte telle quelle, ce qui sous Windows peut lancer un programme local ou réseau.
- explorer.exe est lancé depuis le dossier Windows indiqué par Windows, et non par la variable d'environnement SystemRoot.
- Compilation : chaque paquet Python (dépendances comprises) est figé par l'empreinte SHA-256 de ses fichiers et installé uniquement depuis des wheels, dans GitHub Actions comme dans build.bat ; les actions GitHub sont figées par commit au lieu d'une étiquette modifiable.

## 1.9.2 (2026-10-20)

Nettoyage du code (aucun changement dans ce que fait l'application)
- Code mort supprimé : fonctions Windows qui n'étaient plus appelées (prise en compte du DPI, test d'existence d'une fenêtre, lecture de l'icône d'une fenêtre et son message avec délai), une fonction d'arrêt forcé inutilisée, la recherche de raccourci en double, un champ de liste et un indicateur de bouton jamais lus, et deux textes laissés par les anciens boutons de l'Explorateur.
- Code partagé au lieu de copies : une seule définition de ce qu'ont en commun fenêtres et cibles de fermeture, un seul style d'interrupteur, un seul en-tête de page, une seule liste défilante, un seul en-tête d'image pour les icônes, une seule règle de séparateur décimal, et des paramètres booléens déduits des valeurs par défaut.
- L'écran Arrière-plan lit les processus sur un fil d'exécution séparé : la fenêtre reste réactive pendant qu'il ouvre chaque processus, et la liste actuelle reste affichée jusqu'à ce que la nouvelle soit prête.
- Le redémarrage de l'Explorateur lit la session Windows une seule fois au lieu de le faire à chaque vérification.

## 1.9.1 (2026-10-20)

Corrections issues de l'analyse de la 1.9.0
- Raccourci « Tout fermer » : quand des fenêtres n'ont pas pu être fermées (applications lancées en administrateur, par exemple), un message indique maintenant lesquelles. Le raccourci s'exécute sans fenêtre, donc un échec passait inaperçu ; les détails restent dans le journal.
- Raccourci « Tout fermer » et `--no-ui --all` : CloseAllPython lui-même n'est plus fermé, le raccourci ne ferme donc plus la fenêtre de l'application ouverte. `--close` peut toujours la viser par son titre.
- Paramètres › Raccourci : le raccourci est retrouvé quelle que soit la langue dans laquelle il a été créé (« Tout fermer » ou « Close everything ») ; *Créer le raccourci* le met à jour au lieu d'en ajouter un second, et *Épingler à la barre des tâches…* reste disponible après un changement de langue.
- Écran Arrière-plan : un processus sans fenêtre n'est plus masqué parce qu'un autre processus du même exécutable a une fenêtre (un service Python pendant qu'un programme Python est ouvert, par exemple). Les processus annexes sont maintenant rattachés à l'application qui les a lancés ; les processus de Windows comme l'Explorateur ne comptent jamais comme cette application.
- Écran Arrière-plan : formulation correcte avec un seul processus (« Celui qui utilise le plus de mémoire »).
- GitHub Actions : les exécutables sont compilés et lancés à chaque push (`--self-test` : chaque module, la liste des fenêtres, la mémoire des processus, les sessions et l'objet COM du raccourci, plus `--version` et `--no-ui --all --dry-run`), et une release publie exactement ces fichiers testés.

## 1.9.0 (2026-10-20)

Redémarrer l'Explorateur de fichiers
- Nouveau bouton **Redémarrer** dans la barre du bas de la liste des applications, à côté du bouton qui ferme les fenêtres de l'Explorateur ; les deux sont maintenant regroupés sous le titre « Explorateur de fichiers » avec des libellés plus courts, pour garder de la place quand la fenêtre est petite.
- Après confirmation, tous les explorer.exe de votre session Windows sont arrêtés (les sessions des autres utilisateurs ne sont pas touchées). Windows relance le shell de lui-même, avec vos droits ; s'il ne l'a pas fait au bout de 8 secondes, l'application démarre explorer.exe. La barre des tâches et le bureau disparaissent quelques secondes et les fenêtres de l'Explorateur se ferment ; les autres applications continuent de fonctionner.
- La barre d'état affiche la progression et le résultat ; la liste s'actualise ensuite. Le redémarrage est inscrit dans le journal.

## 1.8.0 (2026-10-19)

Processus en arrière-plan
- Nouvel écran **Arrière-plan** (barre de gauche) : les 10 processus sans aucune fenêtre qui utilisent le plus de mémoire, du plus gros au plus petit, avec icône, nom, PID, mémoire et une barre pour les comparer. Le résumé indique combien de processus tournent en arrière-plan et la mémoire qu'ils utilisent au total.
- La mémoire est le jeu de travail privé, la colonne « Mémoire » du Gestionnaire des tâches. Elle est lue en un seul appel système qui ne demande aucun accès aux processus : les services et processus protégés sont donc mesurés aussi, sans droits administrateur.
- Les processus annexes d'une application qui a une fenêtre restent avec cette application (ceux d'un navigateur ou de Steam ne sont pas listés tant que sa fenêtre est ouverte).
- Les processus de Windows (Memory Compression, Explorateur, svchost…) sont exclus par défaut ; l'interrupteur *Inclure les processus de Windows* les affiche, grisés et marqués « Windows ». Le choix est enregistré.
- La liste est lue à chaque ouverture de l'écran et avec *Actualiser*. Elle sert uniquement à consulter : rien n'est fermé depuis cet écran.

## 1.7.0 (2026-10-17)

Raccourci « Tout fermer »
- Nouvelle section **Raccourci** dans les paramètres : *Créer le raccourci* place un raccourci « Tout fermer » sur le Bureau. Son exécution lance l'application sans aucune fenêtre (`--no-ui --all -y`) et ferme instantanément de force toutes les fenêtres ouvertes, sans confirmation ; les processus protégés de Windows restent ignorés. Le travail non enregistré est perdu, comme l'indique la section.
- *Épingler à la barre des tâches…* affiche le raccourci dans l'Explorateur de fichiers avec les étapes pour l'épingler : clic droit › « Épingler à la barre des tâches » (Windows 11 : « Afficher plus d'options » d'abord), ou glisser-déposer sur la barre des tâches. Windows ne permet pas à un programme de s'épingler lui-même : ce dernier clic reste à vous.
- Le raccourci pointe vers l'application à son emplacement d'installation : les mises à jour remplacent le fichier sur place, il continue donc de fonctionner. Si vous déplacez l'application, recréez le raccourci.
- Depuis les sources, le raccourci exécute `pythonw.exe closeallpython.py` avec les mêmes options.

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
