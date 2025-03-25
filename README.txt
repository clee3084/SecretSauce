Product Hunt Consumer Filter API
============================

1. Vision & Mission
------------------
Our mission is to help venture capital investors efficiently discover and track consumer-focused products and startups on Product Hunt. While Product Hunt hosts a wide variety of products across B2B and B2C sectors, our API specifically filters for consumer-focused innovations, making it easier for consumer-focused VCs to identify potential investment opportunities.

The vision is to streamline the deal discovery process by automatically filtering out B2B/enterprise products and surfacing truly consumer-focused innovations across categories like:
- Personal productivity
- Entertainment
- Education
- Lifestyle
- Social networking
- Consumer apps
- Shopping and e-commerce

2. System Components & Technical Architecture
------------------------------------------
Languages and Technologies:
- Python 3.x: Main programming language
  * requests: HTTP client library for API communication
  * python-dotenv: Environment variable management
  * json: Data serialization and storage
- GraphQL: Query language for Product Hunt API v2
  * Efficient data fetching with specific field selection
  * Reduced network overhead compared to REST
- JSON: Data storage format
  * Human-readable format for easy inspection
  * Structured data for analytics
  * Compatible with most data analysis tools
- Environment Variables (.env): Secure credential storage
  * Prevents hardcoding of sensitive information
  * Easy configuration management
  * Supports different environments (dev/prod)

Key Components:

a) Authentication System:
   - Uses Product Hunt's Developer Token for API access
   - Credentials stored securely in .env file
   - Token-based authentication with Bearer scheme
   - Automatic token inclusion in API requests
   - Session management for connection persistence

b) API Integration Layer:
   - Connects to Product Hunt's GraphQL API v2
   - Features:
     * Custom HTTP headers for authentication
     * User-Agent simulation for reliability
     * Error handling and retry logic
     * Rate limiting compliance
   - GraphQL Query Optimization:
     * Selective field fetching
     * Complexity management
     * Batch size optimization

c) Data Storage System:
   - Local Storage Architecture:
     * data/
       ├── products_batch_[timestamp].json  # Individual batch results
       └── summary.json                     # Analytics and statistics
   
   - Batch Files (products_batch_[timestamp].json):
     * Timestamped for historical tracking
     * Contains full product details:
       - Product ID and name
       - Description and tagline
       - Vote counts
       - Topics and categories
       - Scraping timestamp
   
   - Summary File (summary.json):
     * Real-time statistics:
       - Total products processed
       - Consumer product count
       - Unique topics distribution
       - Latest update timestamp

d) Filtering Engine:
   - Two-Stage Filtering Process:
     1. Category-based filtering (primary)
     2. Keyword-based analysis (secondary)
   
   - Implementation Details:
     * Set operations for O(1) category lookups
     * Regular expressions for keyword matching
     * Case-insensitive text analysis
     * Configurable filtering rules

3. Filtering Criteria
--------------------
Products are filtered through a sophisticated multi-layer system:

a) Category Exclusion System:
   Primary Categories:
   - Developer Tools
   - SaaS
   - Enterprise
   - B2B
   - Business Intelligence
   
   Technical Categories:
   - Analytics
   - Operations
   - Infrastructure
   - Development Tools
   - DevOps
   - Cloud Computing
   
   Business Categories:
   - Human Resources
   - Legal/Accounting
   - Fintech/Payments
   - Security
   - Customer Communication
   - Sales/Marketing Tools
   
   Integration Categories:
   - API Tools
   - Database
   - No-Code/Low-Code
   - Maker Tools
   - Design Tools
   - Marketing Automation

b) Keyword Filtering System:
   Business Terms:
   - enterprise
   - business
   - company
   - workflow
   - management
   
   Technical Terms:
   - api
   - integration
   - infrastructure
   - developer
   - development
   
   Operations Terms:
   - dashboard
   - analytics
   - security
   - team
   
   Context Analysis:
   - Examines both description and tagline
   - Considers keyword context
   - Weights multiple matches
   - Handles common variations

c) Positive Indicators (Products More Likely to Pass):
   - Direct consumer benefit
   - Personal use cases
   - Individual user focus
   - Entertainment value
   - Lifestyle enhancement
   - Personal productivity
   - Social features

4. Usage Guide
-------------
Detailed Setup and Operation:

Prerequisites:
1. Python Environment:
   - Python 3.x installed
   - pip (Python package manager)
   - Virtual environment recommended
   
2. Required Packages:
   ```bash
   pip install requests python-dotenv
   ```

3. Product Hunt API Credentials:
   - Developer account required
   - API access approval needed
   - Rate limits understanding

Initial Setup:
1. Repository Setup:
   ```bash
   git clone [repository_url]
   cd product-hunt-consumer-filter
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Environment Configuration:
   Create .env file:
   ```
   PRODUCT_HUNT_TOKEN=your_developer_token
   PRODUCT_HUNT_API_KEY=your_api_key
   PRODUCT_HUNT_API_SECRET=your_api_secret
   ```

Running the API:
1. Basic Operation:
   ```bash
   python product_hunt_api.py
   ```

2. Scheduled Operation:
   - Using cron (Linux/Mac):
     ```
     0 * * * * cd /path/to/api && python product_hunt_api.py
     ```
   - Using Task Scheduler (Windows):
     * Create basic task
     * Set trigger: Daily
     * Action: Start program
     * Program: python.exe
     * Arguments: product_hunt_api.py

Output Structure:
1. Batch Files (data/products_batch_[timestamp].json):
   ```json
   [
     {
       "id": "123456",
       "name": "Product Name",
       "tagline": "Product Tagline",
       "description": "Full description...",
       "votesCount": 100,
       "topics": {
         "edges": [
           {
             "node": {
               "name": "Category1"
             }
           }
         ]
       },
       "scraped_date": "2025-03-24T20:44:56.092864"
     }
   ]
   ```

2. Summary File (data/summary.json):
   ```json
   {
     "total_products": 20,
     "consumer_products": 6,
     "scraping_date": "2025-03-24T20:44:56.092864",
     "unique_topics": ["Topic1", "Topic2"]
   }
   ```

API Limitations and Best Practices:
1. Rate Limiting:
   - Maximum 20 products per request
   - Hourly execution recommended
   - GraphQL complexity limit: 500,000
   - Respect Product Hunt's fair use policy

2. Error Handling:
   - Automatic retry on network errors
   - Exponential backoff implementation
   - Error logging to file
   - Alert system for critical failures

3. Data Management:
   - Regular data backups
   - Automated cleanup of old batch files
   - Summary file maintenance
   - Data integrity checks

4. Performance Optimization:
   - Run during off-peak hours
   - Use connection pooling
   - Implement request caching
   - Monitor memory usage

Customization Options:
1. Category Filtering:
   ```python
   EXCLUDED_CATEGORIES.add('new_category')
   EXCLUDED_CATEGORIES.remove('existing_category')
   ```

2. Keyword Filtering:
   ```python
   b2b_keywords.update({'new_keyword1', 'new_keyword2'})
   ```

3. Query Modification:
   ```graphql
   query {
     posts(first: 20) {
       edges {
         node {
           # Add or remove fields here
           id
           name
           # ...
         }
       }
     }
   }
   ```

Troubleshooting:
1. Authentication Issues:
   - Verify token validity
   - Check .env file format
   - Confirm API credentials

2. Rate Limiting:
   - Monitor response headers
   - Implement backoff strategy
   - Adjust batch size

3. Data Quality:
   - Validate JSON structure
   - Check for missing fields
   - Monitor filter effectiveness

For support or questions, please contact: [Your Contact Information]

Note: This API is built on top of Product Hunt's API and follows their terms of service. Please review Product Hunt's API usage guidelines and terms before deployment. 