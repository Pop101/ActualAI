from langchain_community.tools import DuckDuckGoSearchResults#, DuckDuckGoSearchAPIWrapper
from pydantic import BaseModel, Field
from Levenshtein import ratio
from jinja2 import Template
import os
import logging
import time
import json
import re

# Configure logging to console and file (append mode)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('transaction_categorization.log', mode='a'),
        logging.StreamHandler()
    ]
)

# Load configuration from environment variables
LANGCHAIN_MODEL_CODE = os.getenv("LANGCHAIN_MODEL_CODE")
local_vars = {}
exec(LANGCHAIN_MODEL_CODE, {}, local_vars)
llm = local_vars['model']

ACTUAL_SERVER_URL = os.getenv("ACTUAL_SERVER_URL", "http://localhost:5006")
ACTUAL_SERVER_PASSWORD = os.getenv("ACTUAL_SERVER_PASSWORD", "password")
ACTUAL_SERVER_FILE = os.getenv("ACTUAL_SERVER_FILE", "My Finances")

ENABLE_SEARCH = os.getenv("ENABLE_SEARCH", "true").lower().strip() == "true"
SEARCH_REQUEST_DELAY = float(os.getenv("SEARCH_REQUEST_DELAY", 5))  # seconds
SEARCH_RESULT_LIMIT = int(os.getenv("SEARCH_RESULT_LIMIT", 3))

PROMPT_TEMPLATE = Template(os.getenv("PROMPT_TEMPLATE", """
You are an expert at categorizing transactions.
Using the given categories, the bank transaction, and a web search of the payee, make a best-guess attempt to categorize the transaction.
Utilize all information given, including payee name, web search, notes, and amount.

The categories are as follows:
{% for category in categories %}
{{ category.name }}: {{ category.description -}}
{% endfor %}

Note that if the transaction is a transfer, especially one from Venmo or an external account, categorize it as "Cash Transactions" if category available, or "Income" if category is available.
If a transaction is an investment, such as a transfer to a stock brokerage, and there is an "Investment" or "Savings" category available, use that.
If a transaction is a payment to a credit card, set the category to "Nothing".

Here is the transaction:
Name: {{ transaction.payee.name }}
Amount: ${{ transaction.get_amount() }}
Date: {{ transaction.date // 10000 }} - {{ transaction.date % 10000 // 100 }} - {{ transaction.date % 100 }} 
Notes: {{ transaction.notes }}

{% if ENABLE_SEARCH %}
Search Results:
{% for result in search_results %}
Title: {{ result.title }}
Snippet: {{ result.snippet }}

{% endfor %}
{% endif %}

You must respond with a valid JSON, with a category and a confidence.
The category must be exactly one of these categories: {{ categories | map(attribute='name') | join(', ') }}.

The confidence should be on a scale of 0 (least confident) to 10 (most confident).
If you cannot justify exactly one category, return a lower confidence.
Here is an example JSON response:
{
    "reasoning": "All information you used to justify your categorization",
    "category": "Category Name",
    "confidence": 7
}
Model your response after this example, and do not include any other text.
""".strip()))

class TransactionCategorization(BaseModel):
    reasoning: str = Field(description="The reasoning behind the categorization")
    category: str = Field(description="The category for the transaction")
    confidence: float = Field(description="The confidence level of the categorization, on a scale of 0 (least confident) to 10 (most confident)")

LAST_REQUEST_TIME = 0
def rate_limit_request():
    global LAST_REQUEST_TIME
    current_time = time.time()
    if current_time - LAST_REQUEST_TIME < SEARCH_REQUEST_DELAY:
        time.sleep(SEARCH_REQUEST_DELAY - (current_time - LAST_REQUEST_TIME))
    LAST_REQUEST_TIME = current_time

def categorize_transaction(transaction, categories:list) -> dict | None:
    rate_limit_request()
    search = DuckDuckGoSearchResults(backend="html", output_format="list")
    try:
        search_results = search.invoke(transaction.payee.name)
        search_results = search_results[:SEARCH_RESULT_LIMIT]  # Limit results
    except Exception as e:
        logging.error(f"Search error for '{transaction.payee.name}': {e}")
        logging.info("Continuing without search results.")
        search_results = []
    
    prompt = PROMPT_TEMPLATE.render(
        **locals()
    )
    
    # Try structured output first
    try:
        structured_llm = llm.with_structured_output(TransactionCategorization, method="json_mode")
        result = structured_llm.invoke(prompt).dict()
    except (AttributeError, NotImplementedError, Exception) as e:
        response = llm.invoke(prompt)
        try:
            result = json.loads(re.match(r'\{.*\}', response, re.DOTALL).group(0))
        except json.JSONDecodeError:
            logging.error(f"Failed to parse LLM response as JSON: {response}")
            return None
    
    if not isinstance(result, dict) or 'category' not in result:
        return None
    
    # Result is a dictionary with category and confidence (hopefully) -
    # Now lets match the LLM's category to the actual categories (object, not name)
    result['category'] = result['category'].strip()
    result['category'] = max(categories, key=lambda cat: ratio(cat.name, result['category']))
    try:
        result['confidence'] = float(result['confidence'])
    except (ValueError, TypeError):
        result['confidence'] = 0.0
    
    if 'reasoning' not in result or result['reasoning'] is None:
        result['reasoning'] = ""
    
    return result


from actual import Actual
from actual.queries import get_categories, get_transactions, get_accounts

with Actual(base_url=ACTUAL_SERVER_URL, password=ACTUAL_SERVER_PASSWORD, file=ACTUAL_SERVER_FILE) as actual:
    actual.download_budget()
    
    # Get the list of categories
    categories = get_categories(actual.session)
    
    # Categorize all transactions
    for account in get_accounts(actual.session):
        if bool(account.offbudget): continue # Skip offbudget accounts
        for transaction in get_transactions(actual.session, account=account):
            # Skip transactions that are already categorized, have no amount, or are starting balance
            if transaction.payee.name == "Starting Balance": continue
            if transaction.get_amount() == 0: continue
            if transaction.category != None: continue
            logging.warning(transaction.category)
            
            # Get the payee, notes and amount of each transaction
            logging.info(f"Categorizing transaction: {transaction.payee.name} with amount: {transaction.get_amount()}")
            cat = categorize_transaction(transaction, categories)
            if cat is None:
                logging.warning(f"Could not categorize transaction: {transaction.payee.name}")
                continue

            if cat['confidence'] < 5:
                logging.warning(f"Low confidence (cat: {cat['category']} - {cat['confidence']}) for transaction: {transaction.payee.name}")
                continue
            
            # Update the transaction with the new category
            transaction.category = cat['category']
            actual.commit()
            logging.info(f"Categorized transaction: {transaction.payee.name} as {cat['category']} with confidence {cat['confidence']} (reasoning: {cat['reasoning']})")
