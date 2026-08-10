# Project Brief — OpenRunner55

## Problème

Un utilisateur Linux desktop sans smartphone, équipé d'une montre Garmin FR55, doit rallumer un PC Windows (Garmin Express) pour deux flux opposés :

1. **Workouts → Montre :** récupérer les séances créées sur Garmin Connect (web) et les installer sur la FR55.
2. **Montre → Garmin Connect :** remonter les activités et données général enregistrées par la montre vers Garmin Connect pour analyse et suivi.

Sans smartphone, l'application Garmin Connect Mobile n'est pas une alternative. Sans Garmin Express sous Linux, l'utilisateur est bloqué.

## Pour qui

**Un utilisateur : Franck (Leakorn).** Développeur solo sous Linux (Fedora 44, GNOME). Pas de smartphone. Montre Garmin FR55.

La cible est volontairement réduite à un utilisateur unique. Les projets Linux/Garmin existants (garmin-tracker-rs, PiFitSync, garmin-fit-extractor-rpi-zero) oscillent entre 0 et 16 stars GitHub — l'écosystème existe mais est microscopique. Le combo « Linux seul + Garmin sans smartphone » est rare.

**Motivation secondaire :** éprouver la méthode Usage-LLM (SDLC en 7 phases avec agents à personas) sur un projet réel, même si l'utilité pour d'autres est limitée.

## Contexte & Contraintes

### Ce qui est validé

| Élément | Statut | Détail |
|---------|--------|--------|
| Connectivité USB FR55 | ✅ Validé | USB mass storage, partition FAT. Montage natif sous Linux. |
| Copie manuelle .FIT workout → montre | ✅ Validé | Copie dans `GARMIN/Workouts/` → la montre reconnaît le fichier. |
| Copie manuelle firmware → montre | ✅ Validé | Copie de `GUPDATE.GCD` dans `GARMIN/` → la montre installe. |
| API Garmin Connect non-officielle | ✅ Existe | `python-garminconnect` (2711 stars, MIT, maintenu). Méthodes `download_workout()` et `upload_activity()` documentées. |
| SDK FIT officiel | ✅ Existe | `garmin-fit-sdk` (Garmin officiel, Python). Encode/décode .FIT. Backup si l'API ne suffit pas. |

### Ce qui rend le problème non-trivial

- **API non-officielle :** Garmin ne publie pas d'API publique pour Connect. `python-garminconnect` reverse-engineere les endpoints web/mobile. Garmin peut casser ces endpoints à tout moment, sans préavis.
- **Authentification :** Garmin Connect utilise OAuth + MFA potentiel. La robustesse du flow d'auth sur la durée reste à valider.
- **Format FIT binaire :** pas un problème en soi (SDK officiel existe), mais la compatibilité exacte entre un .FIT téléchargé via l'API et ce que la FR55 attend n'est pas prouvée.
- **Firmware stable :** aucune source publique de téléchargement direct hors Garmin Express. Les firmware beta sont sur les forums Garmin, mais les stables ne sont distribués que via Express ou Connect Mobile.

## Hypothèses à valider

| Hypothèse | Statut | Risque si fausse |
|-----------|--------|------------------|
| `python-garminconnect` peut télécharger un workout en .FIT | Probable | Méthode documentée, mais non testée sur ce cas précis. Fallback : `garmin-fit-sdk` pour générer le .FIT soi-même. |
| La FR55 reconnaît un .FIT téléchargé via l'API (vs via Express) | À valider | **Critique.** Si la montre refuse le fichier, le projet doit pivoter vers la génération de .FIT via SDK officiel — faisable mais plus de travail. |
| L'upload d'activités via l'API fonctionne | Probable | Méthode `upload_activity()` documentée. Risque faible. |
| L'authentification Garmin Connect reste stable dans le temps | Probable | Le projet `python-garminconnect` est maintenu depuis des années, mais Garmin peut durcir l'auth à tout moment. |
| Les firmware stables restent inaccessibles hors Express | Probable | Aucune source publique trouvée. La veille firmware se limite donc à une notification. |

## Angles morts identifiés

1. **Test critique non réalisé :** la chaîne `python-garminconnect` → download workout → copie USB → reconnaissance par la montre n'a pas été testée. C'est le point de bascule du projet. À isoler et tester en priorité en Phase 2 (Cadrage).

2. **Dépendance unique à une API non-officielle :** si Garmin ferme ou modifie ses endpoints, le projet perd sa capacité de sync. Pas d'alternative identifiée à ce stade. Mitigation : contribuer au projet `python-garminconnect` si besoin.

3. **Firmware stable — source bloquée :** aucune source publique pour télécharger les firmware stables. La veille se limite à une notification (« une mise à jour est disponible, branche sur Windows »). L'installation automatique de firmware stable est hors périmètre.

4. **Cible ultra-niche :** un utilisateur. Pas de communauté identifiée, pas de retour externe attendu. Le projet vit ou meurt avec un seul utilisateur. Acceptable compte tenu des motivations (usage personnel + éprouver la méthode).

5. **Workflow d'usage réel non observé :** le grilling a porté sur la faisabilité technique, pas sur le détail du workflow utilisateur (création de séance sur Connect, types de séances, fréquence de sync, etc.). À préciser en Phase 2.

## Critères de succès

| Critère | Mesure |
|---------|--------|
| Franck ne rallume plus Windows pour envoyer une séance sur sa FR55 | 0 démarrage Windows pour ce besoin après livraison |
| Franck ne rallume plus Windows pour synchroniser ses activités vers Garmin Connect | 0 démarrage Windows pour ce besoin après livraison |
| L'app notifie les mises à jour firmware stables disponibles | Notification affichée quand une mise à jour est détectée |
| La méthode Usage-LLM a été éprouvée sur un projet complet | Les 7 phases ont été traversées avec retours documentés |

## Hors-périmètre (explicite)

- **Installation automatique de firmware** — risque de briquer la montre, pas de source publique pour les stables. Notification uniquement.
- **Éditeur de séances intégré** — Garmin Connect (web) reste l'éditeur. L'app récupère ce qui est créé sur Connect.
- **Multi-utilisateur / backend serveur** — projet local, mono-utilisateur.
- **Analyse concurrentielle / marché** — pas de marché, projet personnel.
- **Support d'autres montres Garmin** — FR55 uniquement. L'architecture peut le permettre plus tard, mais ce n'est pas un objectif.

## Recommandation

### Go conditionnel

Le problème est réel, personnel et légitime. La chaîne technique est plausible — USB mass storage validé, API non-officielle existante et maintenue, SDK officiel en backup. Les angles morts sont identifiés et étiquetés.

**Condition unique de go :** valider en Phase 2 (Cadrage) le test critique — `python-garminconnect` → download workout → copie USB → reconnaissance par la FR55. Si ce test passe, le projet est viable. S'il échoue, le fallback (génération de .FIT via `garmin-fit-sdk`) reste possible mais augmente significativement la charge de développement.

Le Project Director peut cadrer. Le risque principal est technique et isolable — il ne devrait pas bloquer la phase de conception si le test est mené tôt.
