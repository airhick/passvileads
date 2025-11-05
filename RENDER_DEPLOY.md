# Guide de Déploiement sur Render - Passiv Leads

Ce guide explique comment déployer Passiv Leads (API et Web App) sur Render.

## Configuration Automatique

Le projet est configuré pour fonctionner automatiquement sur Render grâce à `render.yaml`.

### Fichiers de Configuration

- **`render.yaml`** : Configuration principale pour Render
- **`Procfile`** : Commande de démarrage pour gunicorn
- **`requirements.txt`** : Dépendances Python
- **`.gitignore`** : Fichiers à ignorer (base de données, etc.)

## Déploiement

### Option 1 : Via Blueprint (Recommandé)

1. Connectez votre repository GitHub/GitLab/Bitbucket à Render
2. Sur Render Dashboard, cliquez sur **"New"** → **"Blueprint"**
3. Sélectionnez votre repository
4. Render détectera automatiquement `render.yaml`
5. Cliquez sur **"Apply"**

### Option 2 : Via Dashboard

1. Connectez votre repository
2. Cliquez sur **"New"** → **"Web Service"**
3. Configurez :
   - **Name**: `passiv-leads-api`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - **Plan**: Free ou Starter (recommandé)

## Variables d'Environnement

Render configurera automatiquement :
- `PORT` : Défini automatiquement par Render
- `PYTHON_VERSION` : 3.11.7
- `FLASK_ENV` : production
- `SECRET_KEY` : Généré automatiquement par Render

### Variables Optionnelles

Vous pouvez ajouter dans Render Dashboard :
- `DATABASE_PATH` : Chemin personnalisé pour la base de données (par défaut: `passivleads.db`)

## Endpoints Disponibles

Une fois déployé, tous les endpoints sont accessibles :

### Web App
- **Interface Web** : `https://votre-service.onrender.com/`
- **Dashboard** : Accessible depuis l'interface web

### API Endpoints

#### Health Check
```bash
GET /health
```

#### Email Finder
```bash
# Single URL
POST /api/v1/email-finder
Headers: X-API-Key: votre-api-key

# CSV Processing
POST /api/v1/email-finder/csv
Headers: X-API-Key: votre-api-key
```

#### OpenStreetMap Scraper
```bash
POST /api/v1/osm-scraper
Headers: X-API-Key: votre-api-key
```

#### Account Management
```bash
GET /api/v1/account/credits
GET /api/v1/account/usage
GET /api/v1/account/logs
GET /api/v1/account/api-keys
POST /api/v1/account/api-keys
GET /api/v1/account/transactions
```

#### Web Interface API (sans clé API requise)
```bash
GET /api/dashboard/init
POST /api/dashboard/create-api-key
POST /api/dashboard/add-credits
GET /api/autocomplete-city
POST /api/geocode-city
POST /api/scrape-osm-stream
POST /api/process-csv-stream
```

## Base de Données

La base de données SQLite est créée automatiquement lors du premier démarrage. Elle stocke :
- Utilisateurs
- Clés API
- Crédits
- Historique des transactions
- Logs d'utilisation

**Note** : Sur le plan Free, la base de données est persistante mais peut être réinitialisée si le service est supprimé. Pour la production, considérez utiliser PostgreSQL.

## Fonctionnalités

### Web App
- ✅ Interface dark blue/black theme
- ✅ Email Finder avec upload CSV
- ✅ OpenStreetMap Scraper avec carte interactive
- ✅ Dashboard avec gestion des crédits et API keys
- ✅ Visualisation en temps réel des résultats

### API
- ✅ Authentification par clé API
- ✅ Système de crédits
- ✅ Logging des requêtes
- ✅ Gestion des transactions
- ✅ Documentation API intégrée

## Monitoring

### Health Check
L'endpoint `/health` est configuré comme health check path dans Render.

### Logs
Les logs sont accessibles dans Render Dashboard :
- Logs de build
- Logs d'exécution
- Logs d'erreurs

## Performance

### Configuration Gunicorn
- **Workers** : 2 (pour gérer plusieurs requêtes simultanées)
- **Timeout** : 120 secondes (pour les scrapes longs)
- **Logs** : Redirigés vers stdout/stderr

### Optimisations
- Traitement parallèle des URLs
- Streaming pour les grandes réponses
- Mise en cache des résultats (à implémenter si nécessaire)

## Troubleshooting

### Le service ne démarre pas
1. Vérifiez les logs dans Render Dashboard
2. Assurez-vous que toutes les dépendances sont dans `requirements.txt`
3. Vérifiez que la commande de démarrage est correcte

### Erreur "Module not found"
1. Vérifiez que toutes les dépendances sont dans `requirements.txt`
2. Rebuild le service depuis Render Dashboard

### Timeout des requêtes
1. Le timeout est configuré à 120 secondes
2. Pour les scrapes très longs, considérez augmenter le timeout dans `render.yaml`

### Base de données non créée
1. La base de données est créée automatiquement au premier démarrage
2. Vérifiez les permissions d'écriture dans les logs

### Service endormi (Plan Free)
1. Le service s'endort après 15 minutes d'inactivité
2. La première requête peut prendre 30-60 secondes
3. Considérez upgrade au plan Starter pour la production

## Support

Pour plus d'aide :
- [Documentation Render](https://render.com/docs)
- [Support Render](https://render.com/support)
- Logs dans Render Dashboard

