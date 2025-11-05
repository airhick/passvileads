#!/usr/bin/env python3
"""
API Flask pour Email Finder Bot
Déployable sur Render
"""

from flask import Flask, request, jsonify, send_file, render_template_string, Response, stream_with_context, session
from flask_cors import CORS
import logging
import csv
import io
import json
import time
import re
import requests
from urllib.parse import urlparse
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from functools import wraps
from email_finder import EmailFinder
from osm_scraper import OSMScraper
from database import Database

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Créer l'application Flask
app = Flask(__name__)
app.secret_key = 'passivleads-secret-key-change-in-production'
CORS(app)  # Permettre les requêtes CORS

# Initialize database
db = Database()

# Service costs (in USD)
SERVICE_COSTS = {
    'email_finder': 0.01,  # $0.01 per URL
    'email_finder_csv': 0.05,  # $0.05 per CSV file
    'osm_scraper': 0.02,  # $0.02 per city scrape
}

def require_api_key(f):
    """Decorator to require API key authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({
                'error': 'API key required',
                'message': 'Please provide your API key via X-API-Key header or api_key parameter'
            }), 401
        
        user_info = db.validate_api_key(api_key)
        if not user_info:
            return jsonify({
                'error': 'Invalid API key',
                'message': 'The provided API key is invalid or inactive'
            }), 401
        
        # Attach user info to request
        request.user_info = user_info
        return f(*args, **kwargs)
    
    return decorated_function

def check_credits_and_deduct(service: str, cost: float):
    """Check if user has enough credits and deduct them"""
    user_id = request.user_info['user_id']
    current_credits = db.get_user_credits(user_id)
    
    if current_credits < cost:
        return False, jsonify({
            'error': 'Insufficient credits',
            'message': f'You need ${cost:.4f} credits but only have ${current_credits:.4f}',
            'current_credits': current_credits,
            'required_credits': cost
        }), 402
    
    success = db.deduct_credits(user_id, cost, f'{service} API usage')
    if not success:
        return False, jsonify({
            'error': 'Failed to deduct credits',
            'message': 'An error occurred while processing your request'
        }), 500
    
    return True, None, None

# Route de santé pour vérifier que l'API fonctionne
@app.route('/health', methods=['GET'])
def health():
    """Endpoint de santé"""
    return jsonify({
        'status': 'healthy',
        'service': 'Email Finder API'
    }), 200

# Route principale pour trouver les emails
@app.route('/api/find-emails', methods=['GET', 'POST'])
def find_emails():
    """
    Endpoint principal pour trouver les emails sur un site web
    
    GET params ou POST body:
    - url: URL du site à scraper (requis)
    - max_pages: Nombre maximum de pages à visiter (optionnel, défaut: 10)
    - timeout: Timeout pour les requêtes HTTP en secondes (optionnel, défaut: 10)
    
    Returns:
    JSON avec les emails trouvés et les métadonnées
    """
    try:
        # Récupérer les paramètres
        if request.method == 'POST':
            data = request.get_json() or {}
            url = data.get('url') or request.args.get('url')
            max_pages = data.get('max_pages') or request.args.get('max_pages', 10, type=int)
            timeout = data.get('timeout') or request.args.get('timeout', 10, type=int)
        else:
            url = request.args.get('url')
            max_pages = request.args.get('max_pages', 10, type=int)
            timeout = request.args.get('timeout', 10, type=int)
        
        # Valider l'URL
        if not url:
            return jsonify({
                'error': 'URL manquante',
                'message': 'Veuillez fournir une URL via le paramètre "url"',
                'example': '/api/find-emails?url=https://example.com'
            }), 400
        
        # Valider le format de l'URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return jsonify({
                    'error': 'URL invalide',
                    'message': 'L\'URL doit contenir un schéma (http:// ou https://)',
                    'example': 'https://example.com'
                }), 400
        except Exception as e:
            return jsonify({
                'error': 'URL invalide',
                'message': str(e)
            }), 400
        
        # Valider max_pages
        if max_pages < 1 or max_pages > 500:
            return jsonify({
                'error': 'max_pages invalide',
                'message': 'max_pages doit être entre 1 et 500'
            }), 400
        
        logger.info(f"Requête pour scraper: {url} (max_pages: {max_pages})")
        
        # Créer l'instance du finder
        finder = EmailFinder(url, max_pages=max_pages, timeout=timeout)
        
        # Lancer le crawl
        results = finder.crawl()
        
        # Retourner les résultats
        return jsonify({
            'success': True,
            'url': url,
            'results': {
                'total_emails': results['total_emails'],
                'emails': results['emails_found'],
                'pages_scraped': results['pages_scraped'],
                'important_pages': results['important_pages']
            }
        }), 200
        
    except ValueError as e:
        logger.error(f"Erreur de validation: {e}")
        return jsonify({
            'error': 'Erreur de validation',
            'message': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}", exc_info=True)
        return jsonify({
            'error': 'Erreur serveur',
            'message': 'Une erreur est survenue lors du scraping',
            'details': str(e) if app.debug else None
        }), 500

# Route alternative avec l'URL dans le path (pour Render)
@app.route('/api/find-emails/<path:url>', methods=['GET'])
def find_emails_from_path(url):
    """
    Endpoint alternatif avec l'URL dans le chemin
    
    Exemple: /api/find-emails/https://example.com
    """
    try:
        # Ajouter le schéma si manquant
        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url
        
        # Récupérer les autres paramètres
        max_pages = request.args.get('max_pages', 10, type=int)
        timeout = request.args.get('timeout', 10, type=int)
        
        # Valider l'URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return jsonify({
                    'error': 'URL invalide',
                    'message': 'L\'URL doit contenir un schéma (http:// ou https://)',
                    'example': 'https://example.com'
                }), 400
        except Exception as e:
            return jsonify({
                'error': 'URL invalide',
                'message': str(e)
            }), 400
        
        # Valider max_pages
        if max_pages < 1 or max_pages > 500:
            return jsonify({
                'error': 'max_pages invalide',
                'message': 'max_pages doit être entre 1 et 500'
            }), 400
        
        logger.info(f"Requête pour scraper: {url} (max_pages: {max_pages})")
        
        # Créer l'instance du finder
        finder = EmailFinder(url, max_pages=max_pages, timeout=timeout)
        
        # Lancer le crawl
        results = finder.crawl()
        
        # Retourner les résultats
        return jsonify({
            'success': True,
            'url': url,
            'results': {
                'total_emails': results['total_emails'],
                'emails': results['emails_found'],
                'pages_scraped': results['pages_scraped'],
                'important_pages': results['important_pages']
            }
        }), 200
        
    except ValueError as e:
        logger.error(f"Erreur de validation: {e}")
        return jsonify({
            'error': 'Erreur de validation',
            'message': str(e)
        }), 400
        
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}", exc_info=True)
        return jsonify({
            'error': 'Erreur serveur',
            'message': 'Une erreur est survenue lors du scraping',
            'details': str(e) if app.debug else None
        }), 500

# Fonction pour détecter automatiquement la colonne URL
def detect_url_column(fieldnames: List[str], sample_rows: List[Dict]) -> Optional[str]:
    """
    Détecte automatiquement la colonne contenant le plus d'URLs
    en analysant les 5 premières lignes du CSV
    """
    url_pattern = re.compile(
        r'https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,}'
    )
    
    column_url_counts = {}
    
    for col in fieldnames:
        column_url_counts[col] = 0
        for row in sample_rows[:5]:  # Analyser les 5 premières lignes
            value = str(row.get(col, '')).strip()
            if value and url_pattern.search(value):
                # Vérifier si ça ressemble vraiment à une URL
                if 'http://' in value or 'https://' in value or '.' in value and len(value.split('.')) >= 2:
                    column_url_counts[col] += 1
    
    # Retourner la colonne avec le plus d'URLs
    if column_url_counts:
        best_column = max(column_url_counts.items(), key=lambda x: x[1])
        if best_column[1] > 0:
            logger.info(f"Colonne URL détectée automatiquement: '{best_column[0]}' ({best_column[1]} URLs trouvées)")
            return best_column[0]
    
    return None

# Route pour traiter un CSV avec streaming
@app.route('/api/process-csv-stream', methods=['POST'])
def process_csv_stream():
    """
    Endpoint pour traiter un fichier CSV avec streaming des résultats en temps réel
    Utilise Server-Sent Events (SSE) pour les mises à jour live
    """
    def generate():
        try:
            # Vérifier qu'un fichier a été uploadé
            if 'file' not in request.files:
                yield f"data: {json.dumps({'error': 'Fichier manquant', 'type': 'error'})}\n\n"
                return
            
            file = request.files['file']
            
            if file.filename == '' or not file.filename.lower().endswith('.csv'):
                yield f"data: {json.dumps({'error': 'Fichier CSV invalide', 'type': 'error'})}\n\n"
                return
            
            # Lire le CSV
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
            csv_reader = csv.DictReader(stream)
            fieldnames = csv_reader.fieldnames
            
            if not fieldnames:
                yield f"data: {json.dumps({'error': 'CSV invalide', 'type': 'error'})}\n\n"
                return
            
            # Lire toutes les lignes
            rows = list(csv_reader)
            
            if not rows:
                yield f"data: {json.dumps({'error': 'CSV vide', 'type': 'error'})}\n\n"
                return
            
            # Détecter automatiquement la colonne URL
            url_col = detect_url_column(fieldnames, rows)
            
            if not url_col:
                yield f"data: {json.dumps({'error': 'Aucune colonne URL détectée', 'type': 'error'})}\n\n"
                return
            
            # Envoyer les métadonnées initiales avec les données des lignes
            yield f"data: {json.dumps({'type': 'init', 'total_rows': len(rows), 'url_column': url_col, 'columns': fieldnames, 'rows_data': rows})}\n\n"
            
            # Préparer les résultats (thread-safe)
            results = [None] * len(rows)
            results_lock = threading.Lock()
            processed_count = 0
            
            def process_row(idx: int, row: Dict, url_col: str):
                """Fonction pour traiter une ligne de manière thread-safe"""
                nonlocal processed_count
                row_copy = row.copy()
                url = row_copy.get(url_col, '').strip()
                
                if not url:
                    row_copy['email'] = ''
                    with results_lock:
                        results[idx - 1] = row_copy
                        processed_count += 1
                    return {'row': idx, 'data': row_copy, 'status': 'skipped'}
                
                # Ajouter le schéma si manquant
                if not url.startswith('http://') and not url.startswith('https://'):
                    url = 'https://' + url
                
                try:
                    # Scraper l'URL
                    finder = EmailFinder(url, max_pages=10, timeout=10)
                    found_emails = finder.find_emails()
                    
                    # Joindre les emails avec des sauts de ligne
                    email_str = '\n'.join(found_emails) if found_emails else ''
                    row_copy['email'] = email_str
                    
                    with results_lock:
                        results[idx - 1] = row_copy
                        processed_count += 1
                    
                    return {'row': idx, 'data': row_copy, 'status': 'completed', 'emails_count': len(found_emails)}
                    
                except Exception as e:
                    logger.error(f"Erreur lors du scraping de {url}: {e}")
                    row_copy['email'] = f'ERROR: {str(e)}'
                    with results_lock:
                        results[idx - 1] = row_copy
                        processed_count += 1
                    return {'row': idx, 'data': row_copy, 'status': 'error', 'error': str(e)}
            
            # Traiter toutes les URLs en parallèle (batch de 100)
            max_workers = 100
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Soumettre toutes les tâches
                future_to_row = {}
                for idx, row in enumerate(rows, 1):
                    future = executor.submit(process_row, idx, row, url_col)
                    future_to_row[future] = idx
                
                # Traiter les résultats au fur et à mesure
                for future in as_completed(future_to_row):
                    try:
                        result = future.result()
                        yield f"data: {json.dumps({'type': 'update', 'row': result['row'], 'total': len(rows), 'data': result['data'], 'status': result['status'], 'emails_count': result.get('emails_count', 0), 'error': result.get('error')})}\n\n"
                    except Exception as e:
                        logger.error(f"Erreur dans le traitement: {e}")
                        row_idx = future_to_row[future]
                        row_copy = rows[row_idx - 1].copy()
                        row_copy['email'] = f'ERROR: {str(e)}'
                        results[row_idx - 1] = row_copy
                        yield f"data: {json.dumps({'type': 'update', 'row': row_idx, 'total': len(rows), 'data': row_copy, 'status': 'error', 'error': str(e)})}\n\n"
            
            # Créer le CSV final (s'assurer que toutes les lignes sont traitées)
            # Filtrer les None si nécessaire
            final_results = [r for r in results if r is not None]
            
            output = io.StringIO()
            output_fieldnames = list(fieldnames)
            if 'email' not in output_fieldnames:
                output_fieldnames.append('email')
            
            csv_writer = csv.DictWriter(output, fieldnames=output_fieldnames)
            csv_writer.writeheader()
            csv_writer.writerows(final_results)
            
            csv_output = output.getvalue()
            
            # Envoyer le CSV final
            yield f"data: {json.dumps({'type': 'complete', 'csv': csv_output})}\n\n"
            
        except Exception as e:
            logger.error(f"Erreur inattendue: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# Route pour traiter un CSV (ancien endpoint, gardé pour compatibilité)
@app.route('/api/process-csv', methods=['POST'])
def process_csv():
    """
    Endpoint pour traiter un fichier CSV
    
    Le CSV doit contenir une colonne 'url' (ou 'URL').
    Pour chaque ligne, le bot scrapera l'URL et ajoutera une colonne 'email'
    avec les emails trouvés (séparés par des virgules si plusieurs).
    
    Form data:
    - file: fichier CSV (requis)
    - max_pages: nombre max de pages par site (optionnel, défaut: 10)
    - timeout: timeout en secondes (optionnel, défaut: 10)
    - url_column: nom de la colonne URL (optionnel, défaut: 'url')
    
    Returns:
    CSV avec colonne 'email' ajoutée
    """
    try:
        # Vérifier qu'un fichier a été uploadé
        if 'file' not in request.files:
            return jsonify({
                'error': 'Fichier manquant',
                'message': 'Veuillez fournir un fichier CSV via le paramètre "file"'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'error': 'Fichier vide',
                'message': 'Aucun fichier sélectionné'
            }), 400
        
        if not file.filename.lower().endswith('.csv'):
            return jsonify({
                'error': 'Format invalide',
                'message': 'Le fichier doit être un CSV (.csv)'
            }), 400
        
        # Lire le CSV
        try:
            # Décoder le fichier
            stream = io.StringIO(file.stream.read().decode('utf-8-sig'))  # utf-8-sig pour gérer BOM
            csv_reader = csv.DictReader(stream)
            
            # Vérifier que la colonne URL existe
            fieldnames = csv_reader.fieldnames
            if not fieldnames:
                return jsonify({
                    'error': 'CSV invalide',
                    'message': 'Le CSV est vide ou invalide'
                }), 400
            
            # Lire toutes les lignes pour la détection
            rows = list(csv_reader)
            
            if not rows:
                return jsonify({
                    'error': 'CSV vide',
                    'message': 'Le CSV ne contient aucune ligne de données'
                }), 400
            
            # Détecter automatiquement la colonne URL
            url_col = detect_url_column(fieldnames, rows)
            
            if not url_col:
                return jsonify({
                    'error': 'Colonne URL introuvable',
                    'message': 'Aucune colonne contenant des URLs n\'a été détectée',
                    'colonnes_disponibles': list(fieldnames)
                }), 400
            
            logger.info(f"Traitement de {len(rows)} URLs depuis le CSV en parallèle (colonne détectée: {url_col})")
            
            # Préparer les résultats (thread-safe)
            results = [None] * len(rows)
            results_lock = threading.Lock()
            
            def process_row_legacy(idx: int, row: Dict, url_col: str):
                """Fonction pour traiter une ligne de manière thread-safe (endpoint legacy)"""
                row_copy = row.copy()
                url = row_copy.get(url_col, '').strip()
                
                if not url:
                    row_copy['email'] = ''
                    with results_lock:
                        results[idx - 1] = row_copy
                    return
                
                # Ajouter le schéma si manquant
                if not url.startswith('http://') and not url.startswith('https://'):
                    url = 'https://' + url
                
                try:
                    # Scraper l'URL
                    finder = EmailFinder(url, max_pages=10, timeout=10)
                    found_emails = finder.find_emails()
                    
                    # Joindre les emails avec des sauts de ligne
                    email_str = '\n'.join(found_emails) if found_emails else ''
                    row_copy['email'] = email_str
                    
                    logger.info(f"Ligne {idx}: {len(found_emails)} email(s) trouvé(s)")
                    
                except Exception as e:
                    logger.error(f"Erreur lors du scraping de {url}: {e}")
                    row_copy['email'] = f'ERROR: {str(e)}'
                
                with results_lock:
                    results[idx - 1] = row_copy
            
            # Traiter toutes les URLs en parallèle (batch de 100)
            max_workers = 100
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Soumettre toutes les tâches
                futures = []
                for idx, row in enumerate(rows, 1):
                    future = executor.submit(process_row_legacy, idx, row, url_col)
                    futures.append(future)
                
                # Attendre que toutes les tâches soient terminées
                for future in as_completed(futures):
                    future.result()  # Attendre le résultat
            
            # Filtrer les None si nécessaire
            final_results = [r for r in results if r is not None]
            
            # Créer le CSV de sortie
            output = io.StringIO()
            
            # Ajouter la colonne 'email' aux fieldnames si elle n'existe pas
            output_fieldnames = list(fieldnames)
            if 'email' not in output_fieldnames:
                output_fieldnames.append('email')
            
            csv_writer = csv.DictWriter(output, fieldnames=output_fieldnames)
            csv_writer.writeheader()
            csv_writer.writerows(final_results)
            
            # Préparer la réponse
            output.seek(0)
            csv_output = output.getvalue()
            
            # Créer un fichier en mémoire pour le retour
            mem = io.BytesIO()
            mem.write(csv_output.encode('utf-8-sig'))  # BOM pour Excel
            mem.seek(0)
            
            logger.info(f"CSV traité avec succès: {len(results)} lignes")
            
            return send_file(
                mem,
                mimetype='text/csv',
                as_attachment=True,
                download_name='results_with_emails.csv'
            )
            
        except UnicodeDecodeError:
            return jsonify({
                'error': 'Encodage invalide',
                'message': 'Le fichier CSV doit être encodé en UTF-8'
            }), 400
        except Exception as e:
            logger.error(f"Erreur lors de la lecture du CSV: {e}", exc_info=True)
            return jsonify({
                'error': 'Erreur de traitement CSV',
                'message': 'Une erreur est survenue lors de la lecture du CSV',
                'details': str(e) if app.debug else None
            }), 500
            
    except Exception as e:
        logger.error(f"Erreur inattendue: {e}", exc_info=True)
        return jsonify({
            'error': 'Erreur serveur',
            'message': 'Une erreur est survenue lors du traitement',
            'details': str(e) if app.debug else None
        }), 500

# Route pour l'interface web avec formulaire CSV
@app.route('/', methods=['GET'])
def index():
    """Interface web pour uploader un CSV"""
    # Lire le template depuis le fichier
    import os
    template_path = os.path.join(os.path.dirname(__file__), 'templates_dashboard.html')
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()
    except FileNotFoundError:
        # Fallback si le fichier n'existe pas
        html_template = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Finder - CSV Processor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2em;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 1.1em;
        }
        .upload-section {
            border: 2px dashed #ddd;
            border-radius: 8px;
            padding: 40px;
            text-align: center;
            margin-bottom: 30px;
            transition: all 0.3s;
        }
        .upload-section:hover {
            border-color: #667eea;
            background: #f8f9ff;
        }
        .upload-section.dragover {
            border-color: #667eea;
            background: #f0f4ff;
        }
        input[type="file"] {
            display: none;
        }
        .file-label {
            display: inline-block;
            padding: 12px 24px;
            background: #667eea;
            color: white;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            transition: background 0.3s;
        }
        .file-label:hover {
            background: #5568d3;
        }
        .file-name {
            margin-top: 15px;
            color: #666;
            font-size: 14px;
        }
        .options {
            margin: 20px 0;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        .option-group {
            display: flex;
            flex-direction: column;
        }
        .option-group label {
            margin-bottom: 5px;
            color: #333;
            font-weight: 500;
            font-size: 14px;
        }
        .option-group input {
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
        }
        .submit-btn {
            width: 100%;
            padding: 15px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.3s;
            margin-top: 20px;
        }
        .submit-btn:hover:not(:disabled) {
            background: #5568d3;
        }
        .submit-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .loading {
            display: none;
            text-align: center;
            margin: 20px 0;
            color: #667eea;
        }
        .loading.active {
            display: block;
        }
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .error {
            background: #fee;
            color: #c33;
            padding: 15px;
            border-radius: 6px;
            margin: 20px 0;
            display: none;
        }
        .error.active {
            display: block;
        }
        .success {
            background: #efe;
            color: #3c3;
            padding: 15px;
            border-radius: 6px;
            margin: 20px 0;
            display: none;
        }
        .success.active {
            display: block;
        }
        .download-link {
            display: inline-block;
            margin-top: 10px;
            padding: 10px 20px;
            background: #28a745;
            color: white;
            text-decoration: none;
            border-radius: 6px;
            transition: background 0.3s;
        }
        .download-link:hover {
            background: #218838;
        }
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .info-box h3 {
            margin-bottom: 10px;
            color: #333;
        }
        .info-box ul {
            margin-left: 20px;
            color: #666;
        }
        .info-box li {
            margin: 5px 0;
        }
        @media (max-width: 600px) {
            .options {
                grid-template-columns: 1fr;
            }
            .container {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📧 Email Finder</h1>
        <p class="subtitle">Trouvez les emails sur vos sites web depuis un fichier CSV</p>
        
        <div class="info-box">
            <h3>Comment utiliser :</h3>
            <ul>
                <li>Préparez un fichier CSV avec une colonne "url" (ou "URL")</li>
                <li>Chaque ligne contient une URL à scraper</li>
                <li>Le CSV retourné contiendra une colonne "email" avec les emails trouvés</li>
            </ul>
        </div>
        
        <form id="uploadForm" enctype="multipart/form-data">
            <div class="upload-section" id="uploadSection">
                <input type="file" id="csvFile" name="file" accept=".csv" required>
                <label for="csvFile" class="file-label">📁 Choisir un fichier CSV</label>
                <div class="file-name" id="fileName">Aucun fichier sélectionné</div>
            </div>
            
            <div class="options">
                <div class="option-group">
                    <label for="maxPages">Pages maximum par site :</label>
                    <input type="number" id="maxPages" name="max_pages" value="50" min="1" max="500">
                </div>
                <div class="option-group">
                    <label for="timeout">Timeout (secondes) :</label>
                    <input type="number" id="timeout" name="timeout" value="10" min="1" max="300">
                </div>
            </div>
            
            <div class="option-group">
                <label for="urlColumn">Nom de la colonne URL :</label>
                <input type="text" id="urlColumn" name="url_column" value="url" placeholder="url">
            </div>
            
            <button type="submit" class="submit-btn" id="submitBtn">
                🔍 Rechercher les emails
            </button>
        </form>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Traitement en cours... Cela peut prendre plusieurs minutes selon le nombre d'URLs.</p>
        </div>
        
        <div class="error" id="error"></div>
        <div class="success" id="success">
            <strong>✅ Succès !</strong> Votre fichier CSV a été traité.
            <a href="#" id="downloadLink" class="download-link" download>📥 Télécharger le CSV avec les emails</a>
        </div>
    </div>
    
    <script>
        const fileInput = document.getElementById('csvFile');
        const fileName = document.getElementById('fileName');
        const uploadSection = document.getElementById('uploadSection');
        const form = document.getElementById('uploadForm');
        const loading = document.getElementById('loading');
        const error = document.getElementById('error');
        const success = document.getElementById('success');
        const submitBtn = document.getElementById('submitBtn');
        const downloadLink = document.getElementById('downloadLink');
        
        // Afficher le nom du fichier
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                fileName.textContent = e.target.files[0].name;
            } else {
                fileName.textContent = 'Aucun fichier sélectionné';
            }
        });
        
        // Drag and drop
        uploadSection.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadSection.classList.add('dragover');
        });
        
        uploadSection.addEventListener('dragleave', () => {
            uploadSection.classList.remove('dragover');
        });
        
        uploadSection.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadSection.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                fileName.textContent = e.dataTransfer.files[0].name;
            }
        });
        
        // Soumission du formulaire
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(form);
            
            // Masquer les messages précédents
            error.classList.remove('active');
            success.classList.remove('active');
            loading.classList.add('active');
            submitBtn.disabled = true;
            
            try {
                const response = await fetch('/api/process-csv', {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ message: 'Erreur inconnue' }));
                    throw new Error(errorData.message || `Erreur ${response.status}`);
                }
                
                // Récupérer le CSV
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                
                // Créer un nom de fichier avec timestamp
                const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
                const originalName = fileInput.files[0].name.replace('.csv', '');
                const downloadFileName = `${originalName}_with_emails_${timestamp}.csv`;
                
                downloadLink.href = url;
                downloadLink.download = downloadFileName;
                
                loading.classList.remove('active');
                success.classList.add('active');
                
            } catch (err) {
                loading.classList.remove('active');
                error.textContent = '❌ Erreur: ' + err.message;
                error.classList.add('active');
            } finally {
                submitBtn.disabled = false;
            }
        });
    </script>
</body>
</html>
        """
    return render_template_string(html_template)

# Route pour autocomplete de villes
@app.route('/api/autocomplete-city', methods=['GET'])
def autocomplete_city():
    """
    Autocomplete pour les villes
    Utilise Nominatim pour rechercher des villes
    
    GET params:
    - query: Texte de recherche (requis)
    - limit: Nombre de résultats (optionnel, défaut: 5)
    
    Returns:
    JSON avec liste de suggestions de villes
    """
    try:
        query = request.args.get('query', '').strip()
        limit = request.args.get('limit', 5, type=int)
        
        if not query or len(query) < 2:
            return jsonify({
                'suggestions': []
            }), 200
        
        # Utiliser Nominatim pour l'autocomplete
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': limit,
            'addressdetails': 1,
            'featuretype': 'city,town,village'  # Filtrer pour les villes uniquement
        }
        headers = {
            'User-Agent': 'PassivLeads/1.0'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        suggestions = []
        for item in data:
            # Construire le nom complet de la ville
            display_name = item.get('display_name', '')
            # Extraire juste le nom de la ville et le pays
            name_parts = display_name.split(',')
            city_name = name_parts[0].strip() if name_parts else display_name
            
            # Extraire le pays
            country = ''
            if len(name_parts) > 1:
                country = name_parts[-1].strip()
            
            suggestions.append({
                'name': city_name,
                'full_name': display_name,
                'country': country,
                'lat': float(item.get('lat', 0)),
                'lon': float(item.get('lon', 0)),
                'boundingbox': item.get('boundingbox', [])
            })
        
        return jsonify({
            'suggestions': suggestions
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur lors de l'autocomplete: {e}", exc_info=True)
        return jsonify({
            'error': 'Server error',
            'message': 'An error occurred during autocomplete',
            'suggestions': []
        }), 500

# Route pour géocoder une ville et obtenir son bbox avec détails
@app.route('/api/geocode-city', methods=['GET', 'POST'])
def geocode_city():
    """
    Géocode une ville et retourne ses coordonnées et bounding box
    
    GET params ou POST body:
    - city: Nom de la ville (requis)
    
    Returns:
    JSON avec les coordonnées et bounding box
    """
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            city = data.get('city') or request.args.get('city')
        else:
            city = request.args.get('city')
        
        if not city:
            return jsonify({
                'error': 'City missing',
                'message': 'Please provide a city name via the "city" parameter'
            }), 400
        
        # Utiliser Nominatim directement pour obtenir plus de détails
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': city,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1,
            'polygon_geojson': 1  # Obtenir les polygones pour les limites
        }
        headers = {
            'User-Agent': 'PassivLeads/1.0'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if not data:
            return jsonify({
                'error': 'City not found',
                'message': f'Could not geocode city: {city}'
            }), 404
        
        location = data[0]
        display_name = location.get('display_name', city)
        
        # Extraire la bounding box
        if 'boundingbox' in location:
            bbox = location['boundingbox']
            min_lat, min_lon, max_lat, max_lon = float(bbox[0]), float(bbox[2]), float(bbox[1]), float(bbox[3])
        elif 'lat' in location and 'lon' in location:
            lat = float(location['lat'])
            lon = float(location['lon'])
            offset = 0.045
            min_lat, min_lon, max_lat, max_lon = lat - offset, lon - offset, lat + offset, lon + offset
        else:
            return jsonify({
                'error': 'City not found',
                'message': f'Could not geocode city: {city}'
            }), 404
        
        # Extraire les coordonnées du centre
        center_lat = float(location.get('lat', (min_lat + max_lat) / 2))
        center_lon = float(location.get('lon', (min_lon + max_lon) / 2))
        
        # Obtenir le polygone si disponible (pour les limites administratives)
        geojson = location.get('geojson')
        
        return jsonify({
            'success': True,
            'city': city,
            'display_name': display_name,
            'bbox': {
                'min_lat': min_lat,
                'min_lon': min_lon,
                'max_lat': max_lat,
                'max_lon': max_lon
            },
            'center': {
                'lat': center_lat,
                'lon': center_lon
            },
            'geojson': geojson  # Polygone pour les limites administratives
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur lors du geocoding: {e}", exc_info=True)
        return jsonify({
            'error': 'Server error',
            'message': 'An error occurred during geocoding',
            'details': str(e) if app.debug else None
        }), 500

# Route pour scraper OpenStreetMap avec streaming
@app.route('/api/scrape-osm-stream', methods=['POST'])
def scrape_osm_stream():
    """
    Scrape les entreprises depuis OpenStreetMap avec streaming des résultats en temps réel
    Utilise Server-Sent Events (SSE) pour les mises à jour live
    
    POST body (JSON):
    - city: Nom de la ville (requis)
    - company_types: Liste des types d'entreprises à rechercher (requis)
    - bbox: Bounding box optionnel [min_lat, min_lon, max_lat, max_lon]
    """
    def generate():
        try:
            data = request.get_json()
            
            if not data:
                yield f"data: {json.dumps({'error': 'Invalid request', 'type': 'error'})}\n\n"
                return
            
            city = data.get('city')
            company_types = data.get('company_types', [])
            bbox = data.get('bbox')
            
            if not city:
                yield f"data: {json.dumps({'error': 'City missing', 'type': 'error'})}\n\n"
                return
            
            if not company_types:
                yield f"data: {json.dumps({'error': 'Company types missing', 'type': 'error'})}\n\n"
                return
            
            # Convertir bbox en tuple si fourni
            bbox_tuple = None
            if bbox and isinstance(bbox, list) and len(bbox) == 4:
                bbox_tuple = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            
            # Créer le scraper
            scraper = OSMScraper(city, bbox=bbox_tuple, timeout=30)
            
            # Obtenir le bbox si pas fourni
            if not bbox_tuple:
                yield f"data: {json.dumps({'type': 'geocoding', 'message': f'Geocoding city: {city}'})}\n\n"
                bbox_tuple = scraper.geocode_city()
                if not bbox_tuple:
                    yield f"data: {json.dumps({'error': f'Could not geocode city: {city}', 'type': 'error'})}\n\n"
                    return
            
            min_lat, min_lon, max_lat, max_lon = bbox_tuple
            center_lat = (min_lat + max_lat) / 2
            center_lon = (min_lon + max_lon) / 2
            
            yield f"data: {json.dumps({'type': 'init', 'city': city, 'bbox': {'min_lat': min_lat, 'min_lon': min_lon, 'max_lat': max_lat, 'max_lon': max_lon}, 'center': {'lat': center_lat, 'lon': center_lon}, 'company_types': company_types})}\n\n"
            
            # Scraper les entreprises
            yield f"data: {json.dumps({'type': 'scraping', 'message': 'Scraping OpenStreetMap data...'})}\n\n"
            
            companies = scraper.scrape_companies(company_types)
            
            # Envoyer les résultats par batch pour le streaming
            batch_size = 10
            for i in range(0, len(companies), batch_size):
                batch = companies[i:i + batch_size]
                yield f"data: {json.dumps({'type': 'update', 'companies': batch, 'total': len(companies), 'processed': min(i + batch_size, len(companies))})}\n\n"
            
            # Créer le CSV final
            output = io.StringIO()
            if companies:
                fieldnames = list(companies[0].keys())
                csv_writer = csv.DictWriter(output, fieldnames=fieldnames)
                csv_writer.writeheader()
                csv_writer.writerows(companies)
            
            csv_output = output.getvalue()
            
            # Envoyer le CSV final
            yield f"data: {json.dumps({'type': 'complete', 'total_companies': len(companies), 'csv': csv_output})}\n\n"
            
        except Exception as e:
            logger.error(f"Erreur inattendue lors du scraping OSM: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# ============================================
# API V1 ENDPOINTS (with authentication)
# ============================================

@app.route('/api/v1/email-finder', methods=['POST'])
@require_api_key
def api_v1_email_finder():
    """
    API V1: Find emails from a single URL
    Requires: X-API-Key header
    Cost: $0.01 per request
    """
    try:
        data = request.get_json() or {}
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required', 'message': 'Please provide a URL in the request body'}), 400
        
        # Check credits
        cost = SERVICE_COSTS['email_finder']
        success, error_response, error_code = check_credits_and_deduct('email_finder', cost)
        if not success:
            return error_response, error_code
        
        # Parse parameters
        max_pages = data.get('max_pages', 10)
        timeout = data.get('timeout', 10)
        
        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                db.add_credits(request.user_info['user_id'], cost, 'Refund for invalid URL')
                return jsonify({'error': 'Invalid URL', 'message': 'URL must include http:// or https://'}), 400
        except Exception as e:
            db.add_credits(request.user_info['user_id'], cost, 'Refund for invalid URL')
            return jsonify({'error': 'Invalid URL', 'message': str(e)}), 400
        
        # Scrape emails
        finder = EmailFinder(url, max_pages=max_pages, timeout=timeout)
        results = finder.crawl()
        
        # Log usage
        db.log_usage(
            request.user_info.get('api_key_id'),
            request.user_info['user_id'],
            'email_finder',
            '/api/v1/email-finder',
            cost,
            200,
            json.dumps({'url': url, 'max_pages': max_pages}),
            json.dumps({'total_emails': results['total_emails']})
        )
        
        return jsonify({
            'success': True,
            'url': url,
            'emails': results['emails_found'],
            'total_emails': results['total_emails'],
            'pages_scraped': results['pages_scraped'],
            'credits_used': cost,
            'remaining_credits': db.get_user_credits(request.user_info['user_id'])
        }), 200
        
    except Exception as e:
        logger.error(f"Error in API v1 email finder: {e}", exc_info=True)
        # Refund credits on error
        db.add_credits(request.user_info['user_id'], cost, 'Refund for error')
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/v1/email-finder/csv', methods=['POST'])
@require_api_key
def api_v1_email_finder_csv():
    """
    API V1: Process CSV file with URLs
    Requires: X-API-Key header
    Cost: $0.05 per CSV file
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided', 'message': 'Please upload a CSV file'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check credits
        cost = SERVICE_COSTS['email_finder_csv']
        success, error_response, error_code = check_credits_and_deduct('email_finder_csv', cost)
        if not success:
            return error_response, error_code
        
        # Process CSV
        csv_content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(csv_reader)
        
        if not rows:
            db.add_credits(request.user_info['user_id'], cost, 'Refund for empty CSV')
            return jsonify({'error': 'Empty CSV', 'message': 'CSV file is empty'}), 400
        
        # Detect URL column
        url_column = detect_url_column(rows[:5])
        if not url_column:
            db.add_credits(request.user_info['user_id'], cost, 'Refund for invalid CSV')
            return jsonify({'error': 'No URL column found', 'message': 'Could not detect URL column in CSV'}), 400
        
        # Process URLs
        results = []
        for row in rows:
            url = row.get(url_column, '').strip()
            if url:
                try:
                    finder = EmailFinder(url, max_pages=10, timeout=10)
                    email_results = finder.crawl()
                    found_emails = list(email_results['emails_found'])
                    row['email'] = '\n'.join(found_emails) if found_emails else ''
                except Exception as e:
                    row['email'] = f'Error: {str(e)}'
            
            results.append(row)
        
        # Create output CSV
        output = io.StringIO()
        if results:
            fieldnames = list(results[0].keys())
            csv_writer = csv.DictWriter(output, fieldnames=fieldnames)
            csv_writer.writeheader()
            csv_writer.writerows(results)
        
        csv_output = output.getvalue()
        
        # Log usage
        db.log_usage(
            request.user_info.get('api_key_id'),
            request.user_info['user_id'],
            'email_finder_csv',
            '/api/v1/email-finder/csv',
            cost,
            200,
            json.dumps({'rows': len(rows)}),
            json.dumps({'rows_processed': len(results)})
        )
        
        return send_file(
            io.BytesIO(csv_output.encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='results_with_emails.csv'
        )
        
    except Exception as e:
        logger.error(f"Error in API v1 CSV processing: {e}", exc_info=True)
        cost = SERVICE_COSTS['email_finder_csv']
        db.add_credits(request.user_info['user_id'], cost, 'Refund for error')
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

@app.route('/api/v1/osm-scraper', methods=['POST'])
@require_api_key
def api_v1_osm_scraper():
    """
    API V1: Scrape OpenStreetMap data for a city
    Requires: X-API-Key header
    Cost: $0.02 per request
    """
    try:
        data = request.get_json() or {}
        city = data.get('city')
        company_types = data.get('company_types', [])
        bbox = data.get('bbox')
        
        if not city:
            return jsonify({'error': 'City is required', 'message': 'Please provide a city name'}), 400
        
        if not company_types:
            return jsonify({'error': 'Company types required', 'message': 'Please provide at least one company type'}), 400
        
        # Check credits
        cost = SERVICE_COSTS['osm_scraper']
        success, error_response, error_code = check_credits_and_deduct('osm_scraper', cost)
        if not success:
            return error_response, error_code
        
        # Convert bbox if provided
        bbox_tuple = None
        if bbox and isinstance(bbox, list) and len(bbox) == 4:
            bbox_tuple = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        
        # Scrape
        scraper = OSMScraper(city, bbox=bbox_tuple, timeout=30)
        if not bbox_tuple:
            bbox_tuple = scraper.geocode_city()
            if not bbox_tuple:
                db.add_credits(request.user_info['user_id'], cost, 'Refund for geocoding failure')
                return jsonify({'error': 'Geocoding failed', 'message': f'Could not geocode city: {city}'}), 400
        
        companies = scraper.scrape_companies(company_types)
        
        # Log usage
        db.log_usage(
            request.user_info.get('api_key_id'),
            request.user_info['user_id'],
            'osm_scraper',
            '/api/v1/osm-scraper',
            cost,
            200,
            json.dumps({'city': city, 'company_types': company_types}),
            json.dumps({'companies_found': len(companies)})
        )
        
        return jsonify({
            'success': True,
            'city': city,
            'companies': companies,
            'total_companies': len(companies),
            'credits_used': cost,
            'remaining_credits': db.get_user_credits(request.user_info['user_id'])
        }), 200
        
    except Exception as e:
        logger.error(f"Error in API v1 OSM scraper: {e}", exc_info=True)
        cost = SERVICE_COSTS['osm_scraper']
        db.add_credits(request.user_info['user_id'], cost, 'Refund for error')
        return jsonify({'error': 'Server error', 'message': str(e)}), 500

# ============================================
# API MANAGEMENT ENDPOINTS
# ============================================

@app.route('/api/v1/account/credits', methods=['GET'])
@require_api_key
def get_account_credits():
    """Get current credit balance"""
    user_id = request.user_info['user_id']
    credits = db.get_user_credits(user_id)
    
    return jsonify({
        'credits': credits,
        'currency': 'USD'
    }), 200

@app.route('/api/v1/account/usage', methods=['GET'])
@require_api_key
def get_account_usage():
    """Get usage statistics"""
    user_id = request.user_info['user_id']
    days = request.args.get('days', 30, type=int)
    stats = db.get_user_usage_stats(user_id, days)
    
    return jsonify(stats), 200

@app.route('/api/v1/account/logs', methods=['GET'])
@require_api_key
def get_account_logs():
    """Get usage logs"""
    user_id = request.user_info['user_id']
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    logs = db.get_user_logs(user_id, limit, offset)
    
    return jsonify({'logs': logs}), 200

@app.route('/api/v1/account/api-keys', methods=['GET'])
@require_api_key
def get_api_keys():
    """Get all API keys for user"""
    user_id = request.user_info['user_id']
    keys = db.get_user_api_keys(user_id)
    
    return jsonify({'api_keys': keys}), 200

@app.route('/api/v1/account/api-keys', methods=['POST'])
@require_api_key
def create_api_key():
    """Create a new API key"""
    user_id = request.user_info['user_id']
    data = request.get_json() or {}
    name = data.get('name', 'API Key')
    
    api_key, _ = db.create_api_key(user_id, name)
    
    return jsonify({
        'api_key': api_key,
        'name': name,
        'message': 'Save this API key securely. It will not be shown again.'
    }), 201

@app.route('/api/v1/account/transactions', methods=['GET'])
@require_api_key
def get_transactions():
    """Get credit transactions"""
    user_id = request.user_info['user_id']
    limit = request.args.get('limit', 50, type=int)
    transactions = db.get_credit_transactions(user_id, limit)
    
    return jsonify({'transactions': transactions}), 200

# ============================================
# WEB DASHBOARD ENDPOINTS
# ============================================

@app.route('/api/dashboard/init', methods=['GET'])
def dashboard_init():
    """Initialize dashboard session (for web interface)"""
    # Create a default user if session doesn't exist
    if 'user_id' not in session:
        # Create default user for web interface
        user_id = db.create_user('web_user', 'web@passivleads.com')
        session['user_id'] = user_id
        session['username'] = 'web_user'
    
    user_id = session['user_id']
    credits = db.get_user_credits(user_id)
    api_keys = db.get_user_api_keys(user_id)
    stats = db.get_user_usage_stats(user_id, 30)
    transactions = db.get_credit_transactions(user_id, 20)
    logs = db.get_user_logs(user_id, 50)
    
    return jsonify({
        'user_id': user_id,
        'username': session.get('username', 'web_user'),
        'credits': credits,
        'api_keys': api_keys,
        'stats': stats,
        'transactions': transactions,
        'logs': logs
    }), 200

@app.route('/api/dashboard/create-api-key', methods=['POST'])
def dashboard_create_api_key():
    """Create API key from dashboard"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    name = data.get('name', 'Web API Key')
    
    user_id = session['user_id']
    api_key, _ = db.create_api_key(user_id, name)
    
    return jsonify({
        'api_key': api_key,
        'name': name
    }), 201

@app.route('/api/dashboard/add-credits', methods=['POST'])
def dashboard_add_credits():
    """Add credits to account (for testing/admin)"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.get_json() or {}
    amount = float(data.get('amount', 0))
    
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    user_id = session['user_id']
    db.add_credits(user_id, amount, 'Manual credit addition')
    
    return jsonify({
        'success': True,
        'credits_added': amount,
        'new_balance': db.get_user_credits(user_id)
    }), 200

# Route pour la documentation API
@app.route('/api', methods=['GET'])
def api_docs():
    """Documentation de l'API"""
    return jsonify({
        'service': 'Email Finder API',
        'version': '1.0.0',
        'endpoints': {
            'health': {
                'method': 'GET',
                'path': '/health',
                'description': 'Vérifier l\'état de l\'API'
            },
            'find_emails': {
                'method': 'GET',
                'path': '/api/find-emails?url=<URL>&max_pages=<NUMBER>',
                'description': 'Trouver les emails sur un site web',
                'parameters': {
                    'url': 'URL du site à scraper (requis)',
                    'max_pages': 'Nombre maximum de pages à visiter (optionnel, défaut: 10, max: 500)',
                    'timeout': 'Timeout en secondes (optionnel, défaut: 10)'
                },
                'examples': [
                    '/api/find-emails?url=https://example.com',
                    '/api/find-emails?url=https://example.com&max_pages=100'
                ]
            },
            'find_emails_post': {
                'method': 'POST',
                'path': '/api/find-emails',
                'description': 'Trouver les emails (POST avec JSON)',
                'body': {
                    'url': 'URL du site à scraper (requis)',
                    'max_pages': 'Nombre maximum de pages (optionnel)',
                    'timeout': 'Timeout en secondes (optionnel)'
                },
                'example': {
                    'url': 'https://example.com',
                    'max_pages': 10
                }
            },
            'process_csv': {
                'method': 'POST',
                'path': '/api/process-csv',
                'description': 'Traiter un fichier CSV avec des URLs et trouver les emails',
                'content_type': 'multipart/form-data',
                'parameters': {
                    'file': 'Fichier CSV avec colonne "url" (requis)',
                    'max_pages': 'Nombre maximum de pages par site (optionnel, défaut: 10)',
                    'timeout': 'Timeout en secondes (optionnel, défaut: 10)',
                    'url_column': 'Nom de la colonne URL (optionnel, défaut: "url")'
                },
                'returns': 'CSV avec colonne "email" ajoutée',
                'example_curl': 'curl -X POST -F "file=@urls.csv" https://votre-api.onrender.com/api/process-csv'
            }
        }
    }), 200

if __name__ == '__main__':
    # Configuration pour le développement
    import os
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)

