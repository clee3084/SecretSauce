import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time
import concurrent.futures
from functools import lru_cache
import logging
from typing import List, Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get developer token
TOKEN = os.getenv('PRODUCT_HUNT_TOKEN')
logger.info(f"Token loaded: {TOKEN[:5]}...")  # Only print first 5 chars for security

# API URL
GRAPHQL_URL = 'https://api.producthunt.com/v2/api/graphql'

# GraphQL query to fetch products with topics
QUERY = '''
{
  posts(
    first: 20,
    featured: true,
    postedAfter: "''' + (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d') + '''"
  ) {
    edges {
      node {
        id
        name
        tagline
        description
        votesCount
        url
        website
        createdAt
        topics {
          edges {
            node {
              name
            }
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
'''

# B2B/Enterprise categories to exclude
EXCLUDED_CATEGORIES = {
    'Developer Tools', 'SaaS', 'Enterprise', 'B2B', 'Business Intelligence',
    'Analytics', 'Operations', 'Human Resources', 'Legal', 'Accounting',
    'Fintech', 'Payments', 'Security', 'Infrastructure', 'API', 'Database',
    'Cloud Computing', 'DevOps', 'GitHub', 'Development', 'Software Engineering',
    'No-Code', 'Maker Tools', 'Design Tools', 'Marketing automation',
    'Customer Communication', 'Sales', 'Business', 'Enterprise Software'
}

# Keywords that suggest B2B/enterprise focus
B2B_KEYWORDS = {
    'enterprise', 'business', 'company', 'team', 'workflow', 
    'management', 'analytics', 'dashboard', 'integration', 'api',
    'developer', 'development', 'infrastructure', 'security'
}

@lru_cache(maxsize=1000)
def is_consumer_product(product: Dict[str, Any]) -> bool:
    """Determine if a product is consumer-focused based on its topics and description."""
    # Get all topics for the product
    topics = {topic['node']['name'] for topic in product['topics']['edges']}
    
    # Check if any excluded categories are present
    if topics & EXCLUDED_CATEGORIES:
        return False
    
    # Check description and tagline for B2B keywords
    text = (product['description'] + ' ' + product['tagline']).lower()
    if any(keyword in text for keyword in B2B_KEYWORDS):
        return False
    
    return True

def fetch_page(cursor: str = None) -> Dict[str, Any]:
    """Fetch a single page of products from the API."""
    current_query = QUERY
    if cursor:
        current_query = current_query.replace(
            'posts(',
            f'posts(after: "{cursor}",'
        )
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {TOKEN}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Origin': 'https://api.producthunt.com',
        'Referer': 'https://api.producthunt.com'
    }
    
    try:
        response = requests.post(
            GRAPHQL_URL,
            json={'query': current_query},
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching page: {str(e)}")
        return None

def process_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process and filter products."""
    # Filter for consumer products
    consumer_products = [product for product in products if is_consumer_product(product)]
    
    # Sort by votes
    consumer_products.sort(key=lambda x: x['votesCount'], reverse=True)
    
    # Add scraping date
    current_time = datetime.now()
    for product in consumer_products:
        product['scraped_date'] = current_time.isoformat()
    
    return consumer_products

def save_data(products: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    """Save products and summary to files."""
    # Create data directory if it doesn't exist
    if not os.path.exists('data'):
        os.makedirs('data')
    
    # Save products to JSON file with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'data/products_batch_{timestamp}.json'
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    
    # Update summary file
    summary_file = 'data/summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Data saved to {filename}")
    logger.info(f"Summary updated in {summary_file}")

def fetch_products():
    """Fetch products from Product Hunt API and save them to JSON files."""
    try:
        all_products = []
        has_next_page = True
        cursor = None
        page = 1
        
        while has_next_page:
            logger.info(f"Fetching page {page}...")
            response_data = fetch_page(cursor)
            
            if not response_data or 'data' not in response_data or 'posts' not in response_data['data']:
                logger.error("Invalid response structure")
                break
            
            # Extract products from this page
            page_products = [edge['node'] for edge in response_data['data']['posts']['edges']]
            all_products.extend(page_products)
            
            # Check if there are more pages
            page_info = response_data['data']['posts']['pageInfo']
            has_next_page = page_info['hasNextPage']
            cursor = page_info['endCursor']
            
            logger.info(f"Fetched {len(page_products)} products from current page")
            logger.info(f"Total products so far: {len(all_products)}")
            
            # Add a small delay to avoid rate limiting
            time.sleep(1)
            page += 1
        
        # Process products
        consumer_products = process_products(all_products)
        logger.info(f"Filtered to {len(consumer_products)} consumer products")
        
        # Prepare summary
        summary = {
            'total_products': len(consumer_products),
            'scraping_date': datetime.now().isoformat(),
            'date_range': {
                'start': (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d'),
                'end': datetime.now().strftime('%Y-%m-%d')
            },
            'filtering_criteria': {
                'excluded_topics': sorted(list(EXCLUDED_CATEGORIES)),
                'excluded_keywords': sorted(list(B2B_KEYWORDS))
            },
            'products': [
                {
                    'name': product['name'],
                    'tagline': product['tagline'],
                    'votes': product['votesCount'],
                    'url': product['url'],
                    'website': product['website'],
                    'created_at': product['createdAt'],
                    'topics': [topic['node']['name'] for topic in product['topics']['edges']]
                }
                for product in consumer_products
            ]
        }
        
        # Save data
        save_data(consumer_products, summary)
        logger.info(f"Successfully fetched {len(consumer_products)} consumer products")
        
    except Exception as e:
        logger.error(f"Error fetching products: {str(e)}")
        logger.error(f"Full error details: {e.__class__.__name__}: {str(e)}")

if __name__ == "__main__":
    fetch_products() 