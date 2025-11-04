# Email Finder Bot

Un bot Python qui scrape un site web pour trouver tous les emails présents, y compris ceux dans les pages de contact, politique de confidentialité, mentions légales, etc.

## Fonctionnalités

- ✅ Crawl automatique de toutes les pages d'un site web
- ✅ Extraction d'emails depuis :
  - Le texte des pages
  - Les liens `mailto:`
  - Les attributs HTML (`data-email`, etc.)
  - Les scripts JavaScript
  - Les commentaires HTML
- ✅ Priorisation des pages importantes (contact, politique, mentions légales, etc.)
- ✅ Filtrage des emails invalides (exemples, placeholders)
- ✅ Respect du même domaine (ne suit pas les liens externes)
- ✅ Gestion des erreurs et logging détaillé

## Installation

1. Installer les dépendances :
```bash
pip install -r requirements.txt
```

## Utilisation

### En ligne de commande

```bash
python email_finder.py <URL>
```

Exemple :
```bash
python email_finder.py https://hanae-restaurant.ch/
```

### Options

- `--max-pages N` : Limiter le nombre de pages à visiter (par défaut: 100)

Exemple :
```bash
python email_finder.py https://example.com --max-pages 50
```

### En tant que module Python

```python
from email_finder import EmailFinder

# Créer une instance
finder = EmailFinder("https://hanae-restaurant.ch/", max_pages=100)

# Trouver les emails
emails = finder.find_emails()

# Ou obtenir des résultats détaillés
results = finder.crawl()
print(f"Emails trouvés: {results['emails_found']}")
print(f"Pages visitées: {results['pages_scraped']}")
```

## Exemple de sortie

```
============================================================
Email Finder Bot
============================================================
URL: https://hanae-restaurant.ch/
Pages maximum: 100
============================================================

2024-01-15 10:30:00 - INFO - Début du crawl de https://hanae-restaurant.ch/
2024-01-15 10:30:01 - INFO - Récupération de: https://hanae-restaurant.ch/
2024-01-15 10:30:01 - INFO - Emails trouvés sur https://hanae-restaurant.ch/: {'info@hanae-restaurant.ch'}
...

============================================================
RÉSULTATS
============================================================
Pages visitées: 15
Emails trouvés: 2

Pages importantes visitées:
  - https://hanae-restaurant.ch/politique-de-confidentialite
  - https://hanae-restaurant.ch/contact

📧 EMAILS TROUVÉS:
------------------------------------------------------------
  ✓ contact@hanae-restaurant.ch
  ✓ info@hanae-restaurant.ch

============================================================
```

## API Web (Flask)

Le bot peut également être déployé comme une API web accessible via HTTP.

### Démarrage local de l'API

```bash
python app.py
```

L'API sera accessible sur `http://localhost:5000`

### Endpoints disponibles

#### 1. Documentation
- **GET** `/` ou `/api` - Documentation de l'API

#### 2. Health Check
- **GET** `/health` - Vérifier l'état de l'API

#### 3. Trouver les emails (GET)
- **GET** `/api/find-emails?url=<URL>&max_pages=<NUMBER>`

Exemples :
```bash
curl "https://votre-api.onrender.com/api/find-emails?url=https://hanae-restaurant.ch/"
curl "https://votre-api.onrender.com/api/find-emails?url=https://example.com&max_pages=100"
```

#### 4. Trouver les emails (avec URL dans le path)
- **GET** `/api/find-emails/<URL>`

Exemple :
```bash
curl "https://votre-api.onrender.com/api/find-emails/https://hanae-restaurant.ch/"
```

#### 5. Trouver les emails (POST)
- **POST** `/api/find-emails`
- Body (JSON):
```json
{
  "url": "https://hanae-restaurant.ch/",
  "max_pages": 50,
  "timeout": 10
}
```

### Réponse API

```json
{
  "success": true,
  "url": "https://hanae-restaurant.ch/",
  "results": {
    "total_emails": 2,
    "emails": [
      "contact@hanae-restaurant.ch",
      "info@hanae-restaurant.ch"
    ],
    "pages_scraped": 15,
    "important_pages": [
      "https://hanae-restaurant.ch/politique-de-confidentialite",
      "https://hanae-restaurant.ch/contact"
    ]
  }
}
```

## Déploiement sur Render

### Méthode 1 : Via Render Dashboard (recommandé)

1. **Connecter votre repository Git**
   - Allez sur [Render Dashboard](https://dashboard.render.com)
   - Cliquez sur "New" → "Web Service"
   - Connectez votre repository GitHub/GitLab/Bitbucket

2. **Configuration du service**
   - **Name**: `email-finder-api` (ou votre choix)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Choisissez un plan (Free disponible)

3. **Variables d'environnement** (optionnel)
   - `PYTHON_VERSION`: `3.11.0`
   - `PORT`: Render le définit automatiquement

4. **Déployer**
   - Cliquez sur "Create Web Service"
   - Render va automatiquement builder et déployer votre API

### Méthode 2 : Via render.yaml (déploiement automatique)

Si vous avez un fichier `render.yaml` dans votre repo, Render le détectera automatiquement :

1. Poussez votre code sur GitHub/GitLab/Bitbucket
2. Sur Render Dashboard, cliquez sur "New" → "Blueprint"
3. Sélectionnez votre repository
4. Render utilisera automatiquement `render.yaml` pour créer le service

### Accéder à l'API déployée

Une fois déployé, votre API sera accessible sur :
```
https://votre-service.onrender.com
```

Exemple d'utilisation :
```bash
# Via paramètre GET
curl "https://votre-service.onrender.com/api/find-emails?url=https://hanae-restaurant.ch/"

# Via path
curl "https://votre-service.onrender.com/api/find-emails/https://hanae-restaurant.ch/"

# Via POST
curl -X POST "https://votre-service.onrender.com/api/find-emails" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://hanae-restaurant.ch/", "max_pages": 50}'
```

### Test de l'API déployée

```bash
# Health check
curl "https://votre-service.onrender.com/health"

# Documentation
curl "https://votre-service.onrender.com/api"
```

## Notes importantes

- Le bot respecte le `robots.txt` implicitement en ne suivant que les liens du même domaine
- Les fichiers non-HTML (PDF, images, etc.) sont ignorés
- Les emails trouvés sont automatiquement normalisés (minuscules)
- Le bot filtre les emails évidents de type "exemple" ou "test"
- Sur Render Free, le service peut s'endormir après 15 minutes d'inactivité (première requête peut être lente)
- Pour éviter l'endormissement, utilisez un service de monitoring ou upgradez au plan Starter

## Structure du projet

```
.
├── app.py                 # Application Flask (API)
├── email_finder.py       # Module principal du bot
├── requirements.txt      # Dépendances Python
├── render.yaml          # Configuration Render (optionnel)
├── Procfile             # Commande de démarrage pour Render
├── README.md            # Documentation
├── example.py           # Exemples d'utilisation
└── .gitignore          # Fichiers à ignorer
```

## Licence

Ce projet est fourni tel quel, sans garantie.

# email_finder
