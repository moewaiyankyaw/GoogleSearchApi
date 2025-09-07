from flask import Flask, request, jsonify, render_template
from urllib.parse import unquote, quote_plus
import requests
from bs4 import BeautifulSoup
import os
import time
import random
from functools import wraps
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Try to import googlesearch, but have fallbacks ready
try:
    from googlesearch import search
    HAS_GOOGLESEARCH = True
    logger.info("googlesearch-python library loaded successfully")
except ImportError:
    HAS_GOOGLESEARCH = False
    logger.warning("googlesearch-python not available, using fallback methods")

# Rate limiting decorator
def rate_limit(max_per_minute=15):
    def decorator(f):
        requests = []
        @wraps(f)
        def wrapped(*args, **kwargs):
            now = time.time()
            # Remove requests older than 1 minute
            requests[:] = [req for req in requests if now - req < 60]
            if len(requests) >= max_per_minute:
                return jsonify({"error": "Rate limit exceeded. Try again in a minute."}), 429
            requests.append(now)
            return f(*args, **kwargs)
        return wrapped
    return decorator

def direct_google_search(query, num_results=5):
    """Fallback direct scraping method when googlesearch library fails"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        encoded_query = quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_query}&num={num_results}"
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        
        # Try different selectors
        selectors = ['div.g', 'div.tF2Cxc', 'div.rc']
        containers = []
        
        for selector in selectors:
            containers = soup.select(selector)
            if containers:
                break
        
        for container in containers[:num_results]:
            try:
                title_elem = container.find('h3') or container.find('a')
                title = title_elem.get_text() if title_elem else "No title"
                
                link_elem = container.find('a')
                link = link_elem.get('href', '') if link_elem else ""
                
                if link.startswith('/url?q='):
                    link = link.split('/url?q=')[1].split('&')[0]
                
                snippet_elem = container.find('div', class_='VwiC3b') or container.find('span', class_='aCOpRe')
                snippet = snippet_elem.get_text() if snippet_elem else "No description available"
                
                results.append({
                    "title": title,
                    "url": link,
                    "description": snippet,
                    "kind": "customsearch#result"
                })
            except Exception as e:
                logger.warning(f"Error parsing result: {e}")
                continue
        
        return results
        
    except Exception as e:
        logger.error(f"Direct search failed: {e}")
        return []

def dummy_search_results(query):
    """Return dummy results for testing when everything else fails"""
    return [
        {
            "title": f"Example result for: {query}",
            "url": "https://example.com",
            "description": "This is a sample result. The actual search might be blocked by Google or Render restrictions.",
            "kind": "customsearch#result"
        },
        {
            "title": "Google Search API Documentation",
            "url": "https://github.com/NvChad/example",
            "description": "Documentation for using search APIs and handling restrictions.",
            "kind": "customsearch#result"
        }
    ]

@app.route('/')
def home():
    """Home endpoint with API documentation"""
    return jsonify({
        "message": "Google Search API - Deployed on Render",
        "version": "2.0.0",
        "status": "active",
        "library_available": HAS_GOOGLESEARCH,
        "endpoints": {
            "/search": "GET - Perform Google search",
            "/search/<query>": "GET - Perform Google search with path parameter",
            "/health": "GET - Health check",
            "/docs": "GET - API documentation page"
        },
        "parameters": {
            "q": "Search query (required)",
            "num": "Number of results (default: 5, max: 10)",
            "lang": "Language code (default: 'en')",
            "sleep": "Delay between requests in seconds (default: 2)"
        },
        "note": "Due to Render restrictions, results may be limited or use fallback methods"
    })

@app.route('/docs')
def docs():
    """HTML documentation page"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Google Search API Docs</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .endpoint { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
            code { background: #eee; padding: 2px 5px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>Google Search API Documentation</h1>
        <p>This API provides Google search functionality with fallback mechanisms for Render deployment.</p>
        
        <div class="endpoint">
            <h3>GET /search?q=query</h3>
            <p>Perform a Google search.</p>
            <p><strong>Example:</strong> <code>/search?q=python+flask&num=5</code></p>
        </div>
        
        <div class="endpoint">
            <h3>GET /health</h3>
            <p>Check API health status.</p>
        </div>
        
        <h2>Note on Render Limitations</h2>
        <p>Due to Render's free tier restrictions and Google's anti-scraping measures, 
        the API might use fallback methods or return limited results.</p>
    </body>
    </html>
    '''

@app.route('/search', methods=['GET'])
@rate_limit(max_per_minute=10)
def search_api():
    """Main search API endpoint with multiple fallbacks"""
    try:
        start_time = time.time()
        
        # Get query parameters
        query = request.args.get('q', '')
        if not query:
            return jsonify({"error": "Missing 'q' parameter"}), 400
        
        num_results = min(int(request.args.get('num', 5)), 10)
        lang = request.args.get('lang', 'en')
        sleep_interval = max(int(request.args.get('sleep', 2)), 2)
        
        logger.info(f"Search request: {query}, num: {num_results}")
        
        results = []
        method_used = "unknown"
        
        # Method 1: Try googlesearch library first
        if HAS_GOOGLESEARCH:
            try:
                search_results = search(
                    term=query,
                    num_results=num_results,
                    lang=lang,
                    advanced=True,
                    sleep_interval=sleep_interval
                )
                
                for result in search_results:
                    results.append({
                        "title": result.title,
                        "url": result.url,
                        "description": result.description,
                        "kind": "customsearch#result"
                    })
                method_used = "googlesearch-library"
                
            except Exception as e:
                logger.warning(f"Google search library failed: {e}")
                method_used = "library-failed"
        
        # Method 2: If library failed or not available, try direct scraping
        if not results and method_used != "library-failed":
            try:
                results = direct_google_search(query, num_results)
                method_used = "direct-scraping" if results else "direct-failed"
            except Exception as e:
                logger.warning(f"Direct scraping failed: {e}")
                method_used = "direct-failed"
        
        # Method 3: If all else fails, return dummy results
        if not results:
            results = dummy_search_results(query)
            method_used = "dummy-results"
        
        response_time = round(time.time() - start_time, 2)
        
        return jsonify({
            "query": query,
            "parameters": {
                "num_results": num_results,
                "lang": lang,
                "sleep_interval": sleep_interval
            },
            "total_results": len(results),
            "results": results,
            "method_used": method_used,
            "response_time": f"{response_time}s",
            "timestamp": time.time(),
            "note": "Results may be limited due to platform restrictions"
        })
        
    except Exception as e:
        logger.error(f"Search API error: {e}")
        return jsonify({"error": "Search service temporarily unavailable"}), 503

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "google-search-api",
        "version": "2.0.0",
        "library_available": HAS_GOOGLESEARCH,
        "timestamp": time.time(),
        "environment": os.getenv('RENDER', 'development')
    })

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(429)
def rate_limit_exceeded(error):
    return jsonify({"error": "Rate limit exceeded. Please wait a minute before making another request."}), 429

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
