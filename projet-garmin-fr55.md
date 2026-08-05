# Garmin FR55 — Gestionnaire d'entraînements et de mises à jour pour Linux

## L'idée en une phrase

Une application de bureau pour Linux qui permet à un possesseur de montre Garmin Forerunner 55 de gérer ses entraînements et les mises à jour de sa montre, sans dépendre de Garmin Express (indisponible sous Linux).

## Le problème

Garmin ne fournit pas d'outil officiel sous Linux. Un utilisateur Linux avec une FR55 se retrouve sans moyen simple pour :
- créer et envoyer des séances d'entraînement sur sa montre ;
- récupérer ses activités ;
- savoir qu'une mise à jour de la montre est disponible et l'installer.

Les solutions existantes sont soit propriétaires et fermées (Garmin Express, Garmin Connect mobile), soit des scripts communautaires partiels et fragiles.

## Ce que l'utilisateur doit pouvoir faire

1. **Connecter sa montre** et que l'application la reconnaisse automatiquement.
2. **Se connecter à son compte Garmin** pour synchroniser ses données.
3. **Créer des séances d'entraînement sportives** et les envoyer dans la montre, pour qu'elles soient prises en compte au redémarrage de celle-ci.
4. **Récupérer ses activités** réalisées avec la montre.
5. **Être informé quand une mise à jour de la montre est disponible**, pouvoir la télécharger et l'appliquer.
6. **Avoir un compte utilisateur** dans l'application elle-même.

## La brique « veille »

Un petit service tourne en arrière-plan pour surveiller la disponibilité des nouveautés (mises à jour de la montre, synchronisation des activités) et prévenir l'utilisateur, plutôt que de l'obliger à vérifier manuellement.

## Sur quoi on veut aboutir

Un livrable réel, pas un POC jetable : une application installable, avec une interface de bureau soignée, un compte utilisateur, un service de fond, et un déploiement allant jusqu'au lancement sur serveur. L'objectif est d'éprouver toute la chaîne — de l'architecture au lancement — sur un domaine peu balisé.

## Périmètre de prudence

- L'application ne dépose sur la montre que des fichiers **officiels Garmin**, jamais modifiés.
- La montre reste maîtresse de la validation et de l'installation de ses propres mises à jour : l'application ne touche jamais directement à la mémoire bas niveau du device.
- La « découverte » d'une mise à jour disponible est une zone incertaine à valider tôt : elle ne doit pas bloquer le reste du projet.

## Hors périmètre (pour cette itération)

- Support d'autres modèles de montres que la FR55.
- Toute manipulation firmware non officielle ou modifiée.
- Reverse-engineering maison des protocoles Garmin.

## Critère de réussite

Un utilisateur Linux lambda, possesseur d'une FR55, installe l'application, crée une séance, l'envoie sur sa montre, la voit prise en compte, et est notifié d'une mise à jour disponible — le tout sans jamais ouvrir un terminal ni Garmin Express.
