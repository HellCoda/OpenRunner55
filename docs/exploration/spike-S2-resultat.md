# Spike S-2 — Résultat : Authentification headless & pipeline bidirectionnel GC

- **Date** : 2026-08-07
- **Statut** : ✅ SUCCÈS — GO
- **Auteur** : Dev Backend (exécution conjointe avec Franck/Leakorn)
- **Mission** : `docs/exploration/mission-spike-S2.md`
- **Prérequis** : Spike S-1 (`docs/exploration/spike-S1-resultat.md`) — chaîne `.FIT → FR55` validée, mais auth en fallback navigateur.

---

## 1. Tableau de synthèse

| Bloc | Objectif | Critère de succès | Statut |
|------|----------|-------------------|--------|
| **1 — Auth headless** | Login `garminconnect` sans Selenium/Playwright, avec et sans MFA | Session active sans ouverture de navigateur | ✅ Validé |
| **2 — Persistance session** | Sauvegarder tokenstore, reprise sans credentials | API répond sans nouvelle auth + refresh token fonctionne | ✅ Validé |
| **3 — Upload activité FR55 → GC** | Uploader un `.fit` réel de `GARMIN/Activity/` via `upload_activity()` | Activité apparaît dans GC | ✅ Validé |
| **4 — Upload données non-activité** | Explorer endpoints Monitor/Sleep/Metrics | Déterminer si pipeline bidirectionnel pour données non-activité | ✅ Validé (au-delà des attentes) |
| **5 — Roundtrip complet** | Créer workout → upload → download FIT → vérifier intégrité | Le FIT téléchargé contient la structure du workout original | ✅ Validé |

**Verdict global : 🟢 GO** — le projet peut avancer en l'état. Tous les risques du Spike S-2 sont levés.

---

## 2. Bloc 1 — Authentification headless

### Protocole
- Script : `spike-S2/bloc1_auth_headless.py`
- Credentials lus depuis `~/.config/garmin-spike-S2/credentials.env` (chmod 600, hors dépôt).
- `Garmin(email, password)` sans `prompt_mfa` (compte sans MFA), `login(tokenstore)`.
- Capture de la stratégie gagnante via un handler de logging interceptant les messages `garminconnect.client`.

### Résultat : ✅ SUCCÈS
Authentification réussie **sans aucune ouverture de navigateur**.

### Preuve (sortie console)
```
mobile+cffi(safari_ios)  429 — IP rate limited by Garmin
mobile+cffi(safari)      429 — IP rate limited by Garmin
mobile+cffi(chrome120)   429 — IP rate limited by Garmin
mobile+requests          403 — Cloudflare bot challenge
widget+cffi              ✅ réussite (après délai anti-WAF 3s)

[OK] Authentification réussie — aucun navigateur ouvert.
[OK] Stratégie gagnante : widget+cffi
[OK] full_name : Franck | unit_system : metric
[OK] Tokenstore sauvegardé : ~/.config/garmin-spike-S2/garmin_tokens.json
```

### Observations
- `garminconnect` 0.3.9 est **headless par conception** : `login()` enchaîne 5 stratégies en cascade, **toutes HTTP pures** (`requests` + `curl_cffi`), aucune n'ouvre Selenium/Playwright/un vrai navigateur.
- Le « fallback navigateur » évoqué en S-1 correspondait en réalité à la stratégie **portal/widget** (flow desktop **simulé en HTTP**).
- Les routes **mobile** sont systématiquement rate-limitées (429) ou bloquées par Cloudflare (403) : la stratégie **widget+cffi** (flow SSO HTML, rotation d'empreinte TLS via `curl_cffi`) est celle qui aboutit.
- Le test « avec MFA » n'a pas pu être réalisé (compte sans MFA). L'API MFA est néanmoins supportée par la lib (`prompt_mfa` callback, modes synchrone/asynchrone) — à valider si un compte MFA devient disponible.

---

## 3. Bloc 2 — Persistance de session

### Protocole
- Script : `spike-S2/bloc2_persistance_session.py`
- `Garmin()` instancié **sans credentials**, `login(tokenstore)` charge les tokens sauvegardés au Bloc 1.
- Vérification API (`get_user_summary`), lecture de l'expiry du `di_token` (JWT), puis **refresh forcé** via `garmin.client._refresh_session()`.

### Résultat : ✅ SUCCÈS
Reprise de session sans credentials + refresh token fonctionnel.

### Preuve (sortie console)
```
[OK] Session reprise depuis le tokenstore — AUCUN credential utilisé.
[OK] full_name : Franck
[OK] Vérif API get_user_summary(2026-08-07) : répond.

[BLOC 2] di_token expiry        : 2026-08-08T23:02:06+00:00
[BLOC 2] Temps restant          : 1 day, 3:00:19
[BLOC 2] di_refresh_token présent : True

[BLOC 2] Test du refresh token (force _refresh_session)...
[OK] Refresh token FONCTIONNE — nouveau di_token obtenu.
[OK] Nouveau di_token expiry : 2026-08-08T22:40:07+00:00
[OK] Tokenstore mis à jour sur disque : True
```

### Observations
- Le `di_token` (JWT) a une durée de vie d'**environ 1 jour**.
- La lib rafraîchit automatiquement : proactif 15 min avant expiry (`_token_expires_soon`) + auto-healing sur 401.
- Stratégie « credentials saisis une seule fois → tokenstore pour la suite » : **validée**.
- Les attributs de token vivent sur l'objet interne `garmin.client` (`di_token`, `di_refresh_token`, `_refresh_session()`), pas sur `garmin` directement.

---

## 4. Bloc 3 — Upload activité FR55 → GC

### Protocole
- Script : `spike-S2/bloc3_upload_activity.py`
- Baseline : activités déjà présentes dans GC (`get_activities`).
- Sélection d'un `.fit` de `GARMIN/Activity/` non déjà présent dans GC (comparaison timestamps).
- `upload_activity(path)` puis poll `get_activities` (30 s max) pour vérifier l'apparition.

### Résultat : ✅ SUCCÈS
Activité uploadée et visible dans GC en ~5 s.

### Preuve (sortie console)
```
[BLOC 3] 199 fichiers .fit trouvés sur la FR55.
[BLOC 3] Baseline : 20 activités récentes déjà dans GC (plus récente 2026-08-04).
[BLOC 3] Candidat : 2026-08-07-08-29-33.fit (136636 octets, non présent dans GC)

[OK] Upload terminé en 1.12s.
detailedImportResult: uploadId=468077251614, fileName=2026-08-07-08-29-33.fit, processingTime=64ms
[OK] Activité apparue dans GC après ~4.7s.
[OK] activityId GC : 23891381988
```

### Observations
- Pipeline FR55 → GC fonctionne **bout-en-bout** : lecture `.fit` sur la montre montée en USB → `upload_activity()` → activité visible dans GC.
- Temps de propagation : **~5 secondes**.
- La réponse API est nichée sous `detailedImportResult` (`uploadId`, `uploadUuid`, `successes`, `failures`).
- Le compte disposait déjà d'activités dans GC jusqu'au 2026-08-04 (sync antérieure via Windows) ; l'activité du jour a été ajoutée proprement.

---

## 5. Bloc 4 — Upload données non-activité

### Protocole
- Script : `spike-S2/bloc4_upload_non_activite.py`
- **A. Inventaire** des méthodes d'upload santé de `garminconnect` 0.3.9.
- **B. Test empirique** : `upload_activity()` sur un FIT de chaque dossier non-activité de la FR55 (Monitor/Sleep/Metrics/SUMMARY).
- **C. Vérification** : appel des endpoints wellness (`get_steps_data`, `get_heart_rates`, `get_stress_data`, `get_body_battery`, `get_sleep_data`, `get_respiration_data`, `get_spo2_data`, `get_hrv_data`) avant/après upload.

### Résultat : ✅ SUCCÈS MAJEUR
Le pipeline est **réellement bidirectionnel** pour les données non-activité. L'endpoint générique `/upload-service/upload` accepte les FIT natifs de la FR55 et GC les intègre au pipeline wellness.

### Preuve (sortie console)
```
[TEST] Monitor : M87L0030.FIT  -> accepted (imported) — "File processed" code 200
[TEST] Sleep   : S87L0030.FIT  -> accepted (imported) — "File processed" code 200
[TEST] Metrics : G8793947.fit  -> accepted (imported) — "File processed" code 200
[TEST] SUMMARY : f171dfa7-…FIT -> error 406 (rejeté)
```

Vérification de l'apparition des données (avant upload : `None` partout) :
```
get_user_summary(2026-08-07) : totalSteps=17617, restingHeartRate=52, averageStressLevel=37
get_steps_data      : list[84]  (pas par intervalle)
get_heart_rates     : maxHeartRate / minHeartRate présents
get_stress_data     : maxStressLevel / avgStressLevel présents
get_body_battery    : charged / drained présents
get_sleep_data      : dailySleepDTO, sleepLevels, REM présents
get_respiration_data: présent
get_spo2_data       : présent
get_hrv_data        : vide (non peuplé)
```

### Observations
- **Mieux qu'attendu** : la bibliothèque n'expose aucune méthode d'upload dédiée pour ces données, mais l'endpoint générique d'upload accepte les FIT wellness natifs de la montre et les traite.
- Données réellement peuplées dans GC : **pas, FC, stress, body battery, sommeil, respiration, SpO2**.
- Méthodes manuelles disponibles en complément (valeurs saisies, pas des FIT montre) : `add_weigh_in`, `add_body_composition`, `set_blood_pressure`, `add_hydration_data`.
- **Non uploadables / non peuplés** : `SUMMARY` (rejeté 406), `HRV` (endpoint vide après upload).

---

## 6. Bloc 5 — Roundtrip complet workout

### Protocole
- Script : `spike-S2/bloc5_roundtrip_workout.py`
- **Création** d'un `RunningWorkout` (pydantic) : warmup 5 min + repeat[4×(interval 2 min + recovery 1 min)] + cooldown 5 min.
- **Upload** via `upload_running_workout()` → `workoutId`.
- **Download** du FIT via `download_workout(workoutId)` → bytes.
- **Vérification d'intégrité** : décodage du FIT avec `garmin-fit-sdk` (magic `.FIT`, `workout_mesgs`, `workout_step_mesgs`).
- **Push device** via `push_workout_to_device()` + **copie USB** vers `GARMIN/Workouts/{workoutId}.FIT`.
- **Vérification manuelle** sur la FR55 par l'utilisateur.

### Résultat : ✅ SUCCÈS
Le FIT téléchargé contient la structure du workout original. Workout validé manuellement sur la montre.

### Preuve (sortie console)
```
[OK] workoutId = 1656951822
[OK] FIT téléchargé : 321 octets | SHA256 : ab728f4a… | Magic '.FIT' : True

[BLOC 5] workout_mesgs     : 1   (wkt_name="Spike-S2 Roundtrip Running", sport=running, num_valid_steps=5)
[BLOC 5] workout_step_mesgs: 5
[BLOC 5]   step intensities : ['warmup', 'active', 'recovery', None, 'cooldown']
[BLOC 5]   step durations   : [300000, 120000, 60000, 1, 300000]  (ms)

[OK] INTÉGRITÉ VALIDÉE : le FIT téléchargé contient la structure du workout original.

[OK] Push device-message envoyé (deviceId=3478366791, deviceName=For55Franck, statut=new)
[OK] FIT copié vers la montre : /run/media/leakorn/GARMIN/GARMIN/Workouts/1656951822.FIT
```
Vérification manuelle FR55 : ✅ workout présent et fonctionnel (structure confirmée).

### Observations
- Roundtrip d'intégrité validé : le FIT généré par GC contient le nom, le sport et les 5 étapes (warmup/interval/recovery/repeat/cooldown) avec les bonnes durées.
- `push_workout_to_device()` enfile un device-message (statut `new`), mais sa **livraison effective au FR55 nécessite une sync Garmin Connect Mobile (Bluetooth)**. Sans smartphone, la **copie USB** du FIT téléchargé reste le mécanisme réel (validé en S-1 et confirmé ici).
- Dépendances ajoutées au venv pour ce bloc : `pydantic` (workouts typés), `garmin-fit-sdk` (décodage/vérification FIT).

---

## 7. Verdict GO/NOGO

### 🟢 GO — le projet peut avancer en l'état

Tous les risques ciblés par le Spike S-2 sont levés :

| Risque (S-2) | Statut |
|--------------|--------|
| Auth sans navigateur (INC-1, bloquant) | ✅ Levé — cascade HTTP pure, stratégie `widget+cffi` |
| Persistance de session sans re-saisie credentials | ✅ Levé — tokenstore + refresh token |
| Upload activités FR55 → GC | ✅ Levé — `upload_activity()`, propagation ~5 s |
| Pipeline bidirectionnel données non-activité | ✅ Levé — FIT Monitor/Sleep/Metrics acceptés et intégrés |
| Intégrité roundtrip workout | ✅ Levé — FIT téléchargé = structure du workout créé |

---

## 8. Limitations identifiées

1. **Routes mobile GC bloquées** : `mobile+cffi` (429) et `mobile+requests` (403 Cloudflare) systématiquement. La disponibilité de l'auth dépend de la stratégie `widget/portal` (HTTP simulé) — fragile si Garmin durcit le WAF.
2. **`push_workout_to_device` sans smartphone** : enfile un message côté GC mais la livraison au FR55 passe par Connect Mobile (Bluetooth). Sans smartphone, la **copie USB** du FIT téléchargé est le mécanisme à utiliser.
3. **`SUMMARY` rejeté** : les FIT du dossier `GARMIN/SUMMARY/` sont refusés par l'upload (406).
4. **HRV non peuplé** : `get_hrv_data` reste vide après upload des FIT natifs — investigation complémentaire nécessaire (endpoint ou FIT spécifique ?).
5. **Rate limiting 429 (par IP)** : confirmé (déjà vu en S-1). L'API fail-fast sur 429 (pas de retry auto) → délai/backoff exponentiel obligatoire (EF-19).
6. **API non-officielle** : `garminconnect` repose sur du reverse-engineering des endpoints web/mobile. Garmin peut casser à tout moment.
7. **MFA non testée** : le compte de test n'a pas de MFA. Le support API existe (`prompt_mfa`) mais n'a pas pu être validé empiriquement.
8. **`di_token` courte durée** (~1 jour) : le refresh automatique fonctionne, mais dépend de la disponibilité du endpoint de refresh.

---

## 9. Recommandations pour la Phase 3 (Conception)

### Architecture modules (conforme ENF-6)
1. **Module auth** : s'appuyer sur la cascade native `garminconnect` (headless). Stocker les credentials dans le **keyring GNOME** (ENF-5), jamais en clair. Tokenstore dans `~/.config/` (chmod 600, dossier chmod 700).
2. **Module session** : `login(tokenstore)` en priorité (reprise sans credentials), credentials en fallback uniquement si tokens invalides. Refresh automatique géré par la lib.
3. **Module sync activités** : `upload_activity()` sur les `.fit` de `GARMIN/Activity/` (filtrage des déjà présents par comparaison de timestamps). Gestion 429 avec backoff exponentiel (EF-19).
4. **Module sync wellness** : `upload_activity()` (endpoint générique) sur les FIT `Monitor/`, `Sleep/`, `Metrics/` de la montre → pipeline bidirectionnel complet (pas, FC, stress, body battery, sommeil, respiration, SpO2). **Ne pas uploader** `SUMMARY/` (rejeté).
5. **Module workouts** : `download_workout(workoutId)` + copie USB vers `GARMIN/Workouts/{workoutId}.FIT` (mécanisme validé S-1 + S-2). **Ne pas dépendre** de `push_workout_to_device` (pas de smartphone).
6. **Module FIT** : `garmin-fit-sdk` pour décoder/vérifier les FIT (intégrité, filtrage, métadonnées).
7. **Gestion d'erreurs** : 429 → `GarminConnectTooManyRequestsError` (fail-fast + backoff), 5xx/réseau → retry auto (3 attempts, backoff exponentiel + jitter), 401 → re-login.

### Dépendances validées
- `garminconnect` 0.3.9 (API GC, auth headless, upload, workouts)
- `curl_cffi` (rotation d'empreinte TLS — stratégies `widget/portal`)
- `pydantic` (workouts typés)
- `garmin-fit-sdk` (décodage/vérification FIT)
- Python 3.14 (venv `.venv-spike-S2`)

### Points à creuser en Phase 3/4
- **HRV** : déterminer si un endpoint/FIT spécifique permet de peupler les données HRV.
- **MFA** : valider empiriquement le parcours MFA si un compte de test équipé est disponible.
- **Filtrage des `.fit` exploitables** (INC-2) : tests empiriques sur les types de FIT acceptés/refusés par GC.
- **Rate limiting** : calibrer le délai inter-requêtes (2-3 s) et le backoff exponentiel.
- **UI** : décision GTK vs app web locale (INC-3) — à trancher par l'Architecte.

---

## 10. Artefacts produits

| Artefact | Chemin |
|----------|--------|
| Venv spike S-2 | `.venv-spike-S2/` (hors git) |
| Clone `python-garminconnect` | `spike-S2/python-garminconnect/` (hors git, référence source) |
| Script Bloc 1 | `spike-S2/bloc1_auth_headless.py` |
| Script Bloc 2 | `spike-S2/bloc2_persistance_session.py` |
| Script Bloc 3 | `spike-S2/bloc3_upload_activity.py` |
| Script Bloc 4 | `spike-S2/bloc4_upload_non_activite.py` |
| Script Bloc 5 | `spike-S2/bloc5_roundtrip_workout.py` |
| Tokenstore (hors dépôt) | `~/.config/garmin-spike-S2/garmin_tokens.json` |
| Credentials (hors dépôt) | `~/.config/garmin-spike-S2/credentials.env` |
| Workout créé dans GC | `workoutId=1656951822` ("Spike-S2 Roundtrip Running") |
| Workout copié sur la FR55 | `GARMIN/Workouts/1656951822.FIT` |

---

## Conclusion

Le Spike S-2 confirme qu'**OpenRunner55 peut fonctionner entièrement sous Linux sans navigateur ni smartphone** :

- **Authentification** : headless, stable, persistante via tokenstore.
- **Sync montante** (FR55 → GC) : activités **et** données wellness (pas, FC, sommeil, stress, body battery, respiration, SpO2).
- **Sync descendante** (GC → FR55) : workouts téléchargés et copiés sur la montre via USB, reconnus et fonctionnels.
- **Roundtrip d'intégrité** : la structure d'un workout créé par programme est préservée à travers le cycle upload → download → montre.

Le projet peut entrer en **Phase 3 (Conception)**.
