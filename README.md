# ActualAI
[![GitHub issues](https://img.shields.io/github/issues/Pop101/ActualAI)](https://github.com/Pop101/ActualAI/issues)

# Table of Contents
- [ActualAI](#actualai)
- [Table of Contents](#table-of-contents)
- [Overview](#overview)
- [Technologies](#technologies)
- [Methodology](#methodology)
  - [Transaction Categorization Process](#transaction-categorization-process)
  - [Web Search Integration](#web-search-integration)
  - [Vector Store Similarity Matching](#vector-store-similarity-matching)
- [Getting Started](#getting-started)
  - [Installation](#installation)
  - [Configuration](#configuration)
    - [Environment Variables](#environment-variables)
      - [Required Variables](#required-variables)
      - [Actual Budget Configuration](#actual-budget-configuration)
      - [Search Configuration](#search-configuration)
      - [Vector Store Configuration](#vector-store-configuration)
      - [Prompt Configuration](#prompt-configuration)

# Overview

ActualAI is an intelligent transaction categorization tool that leverages Large Language Models (LLMs) and web search to automatically categorize financial transactions in Actual Budget. The system uses a combination of machine learning, semantic search, and real-time web data to make informed categorization decisions with confidence scoring.

# Technologies
This project is created with:
- [ActualPy](https://actualpy.readthedocs.io/): 0.16.0
- [LangChain](https://www.langchain.com/): 0.3.23
- [Jinja2](https://jinja.palletsprojects.com/): 3.1.6
- [Python Levenshtein](https://github.com/rapidfuzz/python-Levenshtein): 0.27.1
- [Sentence Transformers](https://www.sbert.net/): 5.1.2

# Methodology

## Transaction Categorization Process

ActualAI employs a multi-step process to categorize financial transactions:

1. **Data Retrieval**: Connects to an Actual Budget server and retrieves uncategorized transactions
2. **Web Search Enhancement**: Performs web searches on payee names to gather contextual information
3. **Vector Similarity Matching**: Optionally uses a vector store to find similar past transactions
4. **LLM Analysis**: Combines all information sources and uses an LLM to determine the most appropriate category
5. **Confidence Scoring**: Returns categorizations with confidence scores (0-10 scale)
6. **Automated Application**: Applies categorizations that meet minimum confidence thresholds

## Web Search Integration

The system integrates with **DuckDuckGo** to perform real-time web searches on payee names. This provides additional context about merchants, vendors, and service providers that helps improve categorization accuracy. Search results are rate-limited to respect API constraints.

## Vector Store Similarity Matching

When enabled, the system builds a vector store of previously categorized transactions using **Sentence Transformers** (all-MiniLM-L6-v2 model). It performs semantic similarity searches to find comparable past transactions, learning from historical categorization patterns.

This embedding model was selected for speed and efficiency, balancing performance with resource usage.

# Getting Started

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Pop101/ActualAI.git
   cd ActualAI
   ```

2. **Install dependencies**

   This project uses Poetry for dependency management. Install dependencies with:
   ```bash
   poetry install
   ```

   Alternatively, you can use pip:
   ```bash
   pip install actualpy langchain langchain-community langchain-ollama duckduckgo-search jinja2 python-levenshtein sentence-transformers
   ```

3. **Set up Actual Budget Server**

    Ensure you have an [Actual Budget](https://actualbudget.org/) server running and accessible. You'll need:
    - Server URL
    - Server password
    - Budget file name

## Configuration

### Environment Variables

ActualAI is configured entirely through environment variables. Create a `.env` file in the project root or set these variables in your environment:

#### Required Variables

**`LANGCHAIN_MODEL_CODE`** (Required)  
Python code that creates a LangChain model instance. Must define a variable named `model`.  

Example:
```python
from langchain_ollama import OllamaLLM
model = OllamaLLM(model="llama2")
```

#### Actual Budget Configuration

**`ACTUAL_SERVER_URL`** (Default: `http://localhost:5006`)  

The URL of your Actual Budget server.

**`ACTUAL_SERVER_PASSWORD`** (Default: `password`)  

The password for your Actual Budget server.

**`ACTUAL_SERVER_FILE`** (Default: `My Finances`)  

The name of your budget file in Actual Budget.

#### Search Configuration

**`ENABLE_SEARCH`** (Default: `true`)  

Enable or disable web search functionality. Set to `false` to skip web searches.

**`SEARCH_REQUEST_DELAY`** (Default: `5`)  

Delay in seconds between search requests to respect rate limits.

**`SEARCH_RESULT_LIMIT`** (Default: `3`)  

Maximum number of search results to include per transaction.

#### Vector Store Configuration

**`USE_VECTORSTORE`** (Default: `false`)  

Enable or disable the vector store for finding similar past transactions. Set to `true` to use historical transaction matching.

**`VECTORSTORE_TEMPLATE`** (Optional)  

Jinja2 template for formatting transactions in the vector store. Default template includes payee name, amount, date, notes, and category.

Example:
```jinja2
Name: {{ transaction.payee.name }}
Amount: ${{ transaction.get_amount() }}
Date: {{ transaction.date // 10000 }} - {{ transaction.date % 10000 // 100 }} - {{ transaction.date % 100 }} 
Notes: {{ transaction.notes }}

Was categorized as: {{ transaction.category.name }}
```

#### Prompt Configuration

**`PROMPT_TEMPLATE`** (Optional)  

Jinja2 template for the LLM prompt. Customize this to adjust how the model receives transaction information and categorization instructions.

Example:
```jinja2
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

{% if USE_VECTORSTORE %}
Here are similar past transactions and their categories:
{% for past_txn in similar_transactions %}
{{ VECTORSTORE_TRANSACTION_TEMPLATE.render(transaction=past_txn) }}

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
```