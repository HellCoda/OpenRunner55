# Spike Garmin FR55 — Résultat

**Date** : 2025-07-18  
**Statut** : ✅ SUCCÈS  
**Auteur** : Dev Backend (exécution conjointe avec Franck/Leakorn)

---

## Contexte

Ce spike technique visait à valider ou invalider le **risque n°1** du projet OpenRunner55 :

> La Forerunner 55 reconnaît-elle un fichier `.FIT` de workout téléchargé via l'API Python non-officielle `garminconnect` ?

L'enjeu est critique. Si la FR55 ignore le fichier, le projet doit pivoter vers le SDK FIT officiel (mono-langage C, plus lourd à intégrer).

---

## Protocole

| Étape | Action | Résultat attendu |
|-------|--------|------------------|
| 1 | Création d'un venv Python isolé (`/tmp/spike-garmin/`) | Environnement propre |
| 2 | Installation de `garminconnect` via pip | OK |
| 3 | Authentification sur Garmin Connect via email/mot de passe | Session ouverte |
| 4 | Téléchargement du workout public `1656079010` (format `.FIT`) | Fichier binaire récupéré |
| 5 | Copie du `.FIT` sur la FR55 dans `/GARMIN/Workouts/1656079010.FIT` | Fichier placé au bon endroit |
| 6 | Débranchement FR55 → vérification manuelle sur la montre | Workout visible |

**Workout utilisé** : [Running 1656079010](https://connect.garmin.com/app/workout/1656079010?workoutType=running)

---

## Résultats

### Étape 3 — Authentification

```
INFO: Authentification en cours...
WARNING: mobile+cffi returned 429: Mobile login returned 429 — IP rate limited by Garmin
WARNING: mobile+requests returned 429: Mobile login returned 429 — IP rate limited by Garmin
INFO: ✅ Authentifié !
```

⚠️ L'API mobile Garmin a renvoyé un **429 Too Many Requests** (rate limiting IP). Le fallback automatique de `garminconnect` a fonctionné — l'authentification classique par navigateur a pris le relais.

### Étape 4 — Téléchargement

```
INFO: Téléchargement du workout 1656079010...
INFO: ✅ Téléchargé : 237 octets
```

Taille typique pour un workout simple à intervalles.

### Étape 5 — Écriture FR55

```
INFO: Écriture vers /run/media/leakorn/GARMIN/GARMIN/Workouts/1656079010.FIT...
INFO: ✅ Fichier écrit
```

Point de montage : `/run/media/leakorn/GARMIN` (montage automatique Fedora 44).

### Étape 6 — Vérification montre

✅ **Confirmé visuellement** — le workout `1656079010` apparaît bien dans le menu de la FR55 (Menu → Entraînement → Workouts).

---

## Observations notables

| Point | Détail | Impact |
|-------|--------|--------|
| Rate limiting 429 | L'API mobile Garmin limite par IP. Le fallback navigateur fonctionne. | Risque modéré si usage intensif. Prévoir un délai entre requêtes. |
| Taille du fichier | 237 octets pour un workout simple | Négligeable |
| Point de montage | `/run/media/$USER/GARMIN` — standard sur Fedora | Aucun problème |
| Permissions | Montage en lecture/écriture par défaut | Aucun obstacle |
| Format du nom de fichier | `{WORKOUT_ID}.FIT` — en majuscules | À respecter strictement |

---

## Conclusion

### 🟢 GO — Le projet peut continuer sur l'API `garminconnect`.

La Forerunner 55 accepte sans problème les fichiers `.FIT` générés par l'API non-officielle, à condition qu'ils soient placés dans le dossier `/GARMIN/Workouts/` avec le bon nom.

Le risque n°1 est levé. Pas besoin de pivoter vers le SDK FIT officiel.

---

## Prochaines étapes

1. **Phase 2 — Conception** : l'Architecte peut maintenant spécifier le service de téléchargement sans contrainte de SDK C.
2. **Intégration au projet** : le code de téléchargement sera intégré proprement dans `src/` (pas de script jetable).
3. **Gestion du rate limiting** : implémenter un délai respectueux entre requêtes (2-3 secondes) + exponential backoff.
4. **Stockage des credentials** : utiliser le keyring système plutôt que la saisie interactive.
