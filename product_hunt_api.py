import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Get developer token
TOKEN = os.getenv('PRODUCT_HUNT_TOKEN')
print(f"Debug - Token loaded: {TOKEN[:5]}...")  # Only print first 5 chars for security

# API URL
GRAPHQL_URL = 'https://api.producthunt.com/v2/api/graphql'

# GraphQL query to fetch products with topics (simplified to reduce complexity)
QUERY = '''
query {
  posts(first: 20) {  # Reduced from 100 to 20
    edges {
      node {
        id
        name
        tagline
        description
        votesCount
        topics {
          edges {
            node {
              name
            }
          }
        }
      }
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

def is_consumer_product(product):
    """Determine if a product is consumer-focused based on its topics and description."""
    # Get all topics for the product
    topics = {topic['node']['name'] for topic in product['topics']['edges']}
    
    # Check if any excluded categories are present
    if topics & EXCLUDED_CATEGORIES:
        return False
    
    # Keywords that suggest B2B/enterprise focus
    b2b_keywords = {'enterprise', 'business', 'company', 'team', 'workflow', 
                   'management', 'analytics', 'dashboard', 'integration', 'api',
                   'developer', 'development', 'infrastructure', 'security'}
    
    # Check description and tagline for B2B keywords
    text = (product['description'] + ' ' + product['tagline']).lower()
    if any(keyword in text for keyword in b2b_keywords):
        return False
    
    return True

def fetch_products():
    """Fetch products from Product Hunt API and save them to JSON files."""
    try:
        # Create data directory if it doesn't exist
        if not os.path.exists('data'):
            os.makedirs('data')
        
        # Headers for GraphQL request
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {TOKEN}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Origin': 'https://api.producthunt.com',
            'Referer': 'https://api.producthunt.com'
        }
        print(f"Debug - Headers prepared: {headers}")
        
        print("Debug - Making GraphQL API request...")
        # Make API request with a session to handle cookies
        session = requests.Session()
        response = session.post(
            GRAPHQL_URL,
            json={'query': QUERY},
            headers=headers
        )
        print(f"Debug - Response status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Debug - Error response: {response.text[:1000]}...")  # Print first 1000 chars of error
            response.raise_for_status()
            
        # Parse response
        response_data = response.json()
        print(f"Debug - Response data: {json.dumps(response_data, indent=2)[:1000]}...")
        
        # Check if response has the expected structure
        if 'data' not in response_data:
            if 'errors' in response_data:
                print("GraphQL Errors:")
                for error in response_data['errors']:
                    print(f"- {error['message']}")
            print(f"Full response: {json.dumps(response_data, indent=2)}")
            return
            
        if 'posts' not in response_data['data']:
            print("Error: Response does not contain 'posts' field")
            print(f"Full response: {json.dumps(response_data, indent=2)}")
            return
            
        if 'edges' not in response_data['data']['posts']:
            print("Error: Response does not contain 'edges' field")
            print(f"Full response: {json.dumps(response_data, indent=2)}")
            return
        
        # Extract products
        products = [edge['node'] for edge in response_data['data']['posts']['edges']]
        print(f"Debug - Fetched {len(products)} total products")
        
        # Filter for consumer products only
        consumer_products = [product for product in products if is_consumer_product(product)]
        print(f"Debug - Filtered to {len(consumer_products)} consumer products")
        
        # Add scraping date to each product
        current_time = datetime.now()
        for product in consumer_products:
            product['scraped_date'] = current_time.isoformat()
        
        # Save products to JSON file with timestamp
        timestamp = current_time.strftime('%Y%m%d_%H%M%S')
        filename = f'data/products_batch_{timestamp}.json'
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(consumer_products, f, indent=2, ensure_ascii=False)
        
        # Update summary file
        summary_file = 'data/summary.json'
        summary = {
            'total_products': len(consumer_products),
            'scraping_date': current_time.isoformat(),
            'unique_topics': sorted(list(set(
                topic['node']['name']
                for product in consumer_products 
                for topic in product['topics']['edges']
            )))
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"Successfully fetched {len(consumer_products)} consumer products")
        print(f"Data saved to {filename}")
        print(f"Summary updated in {summary_file}")
        
    except Exception as e:
        print(f"Error fetching products: {str(e)}")
        print(f"Debug - Full error details: {e.__class__.__name__}: {str(e)}")

if __name__ == "__main__":
    fetch_products() 