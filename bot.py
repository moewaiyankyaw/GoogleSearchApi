from flask import Flask, request, jsonify, render_template
from googlesearch import search
from urllib.parse import unquote
import os
import time
from functools import wraps
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Rate limiting decorator
def rate_limit(max_per_minute=30):
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

@app.route('/')
def home():
    """Home endpoint with API documentation"""
    return jsonify({
        "message": "Google Search API - Deployed on Render",
        "version": "1.0.0",
        "endpoints": {
            "/search": "GET - Perform Google search",
            "/search/<query>": "GET - Perform Google search with path parameter",
            "/health": "GET - Health check",
            "/docs": "GET - API documentation page"
        },
        "parameters": {
            "q": "Search query (required)",
            "num": "Number of results (default: 10, max: 20)",
            "lang": "Language code (default: 'en')",
            "sleep": "Delay between requests in seconds (default: 1)"
        },
        "examples": {
            "basic": "/search?q=python+flask",
            "advanced": "/search?q=python+flask&num=5&lang=en&sleep=1",
            "path": "/search/python%20flask?num=3"
        }
    })

@app.route('/docs')
def docs():
    """HTML documentation page"""
    return render_template('docs.html')

@app.route('/search', methods=['GET'])
@rate_limit(max_per_minute=20)
def search_api():
    """Main search API endpoint"""
    try:
        # Get query parameters
        query = request.args.get('q', '')
        if not query:
            return jsonify({"error": "Missing 'q' parameter"}), 400
        
        num_results = min(int(request.args.get('num', 10)), 20)  # Reduced max for Render
        lang = request.args.get('lang', 'en')
        sleep_interval = max(int(request.args.get('sleep', 1)), 1)  # Minimum 1 second
        
        logger.info(f"Search request: query='{query}', num_results={num_results}")
        
        # Perform search
        results = []
        try:
            search_results = search(
                term=query,
                num_results=num_results,
                lang=lang,
                advanced=True,
                sleep_interval=sleep_interval
            )
            
            # Format results
            for result in search_results:
                results.append({
                    "title": result.title,
                    "url": result.url,
                    "description": result.description,
                    "kind": "customsearch#result"
                })
                
        except Exception as search_error:
            logger.error(f"Search error: {search_error}")
            return jsonify({"error": "Search service temporarily unavailable"}), 503
        
        logger.info(f"Search completed: found {len(results)} results")
        
        return jsonify({
            "query": query,
            "parameters": {
                "num_results": num_results,
                "lang": lang,
                "sleep_interval": sleep_interval
            },
            "total_results": len(results),
            "results": results,
            "timestamp": time.time()
        })
        
    except ValueError:
        return jsonify({"error": "Invalid parameter format"}), 400
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/search/<path:query>', methods=['GET'])
@rate_limit(max_per_minute=20)
def search_path_api(query):
    """Alternative endpoint using path parameter"""
    try:
        # Decode URL-encoded query
        decoded_query = unquote(query)
        
        # Get other parameters
        num_results = min(int(request.args.get('num', 10)), 20)
        lang = request.args.get('lang', 'en')
        sleep_interval = max(int(request.args.get('sleep', 1)), 1)
        
        logger.info(f"Path search request: query='{decoded_query}'")
        
        # Perform search
        results = []
        search_results = search(
            term=decoded_query,
            num_results=num_results,
            lang=lang,
            advanced=True,
            sleep_interval=sleep_interval
        )
        
        # Format results
        for result in search_results:
            results.append({
                "title": result.title,
                "url": result.url,
                "description": result.description,
                "kind": "customsearch#result"
            })
        
        return jsonify({
            "query": decoded_query,
            "parameters": {
                "num_results": num_results,
                "lang": lang,
                "sleep_interval": sleep_interval
            },
            "total_results": len(results),
            "results": results,
            "timestamp": time.time()
        })
        
    except Exception as e:
        logger.error(f"Path search error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "google-search-api",
        "version": "1.0.0",
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
    app.run(host='0.0.0.0', port=port, debug=debug)
