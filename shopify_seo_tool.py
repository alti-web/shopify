#!/usr/bin/env python3
"""
Shopify SEO Tool - Mise à jour en masse des meta titles et descriptions
Utilise l'API GraphQL Admin de Shopify
"""

import os
import json
import time
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)
CORS(app)

SHOPIFY_STORE = os.getenv("SHOPIFY_STORE", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"


def graphql_url(store=None):
    s = store or SHOPIFY_STORE
    return f"https://{s}.myshopify.com/admin/api/{API_VERSION}/graphql.json"


def graphql_request(query, variables=None, store=None, token=None):
    url = graphql_url(store)
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": token or SHOPIFY_ACCESS_TOKEN,
    }
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise Exception(json.dumps(data["errors"], ensure_ascii=False))
    return data["data"]


# ── Queries ──────────────────────────────────────────────────────────────────

PRODUCTS_QUERY = """
query($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        title
        handle
        status
        seo { title description }
      }
    }
  }
}
"""

COLLECTIONS_QUERY = """
query($cursor: String) {
  collections(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        title
        handle
        seo { title description }
      }
    }
  }
}
"""

PAGES_QUERY = """
query($cursor: String) {
  pages(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id
        title
        handle
        seo { title description }
      }
    }
  }
}
"""

BLOGS_QUERY = """
query {
  blogs(first: 20) {
    edges {
      node {
        id
        title
        handle
      }
    }
  }
}
"""

ARTICLES_QUERY = """
query($blogId: ID!, $cursor: String) {
  blog(id: $blogId) {
    title
    articles(first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id
          title
          handle
          seo { title description }
        }
      }
    }
  }
}
"""

# ── Mutations ────────────────────────────────────────────────────────────────

PRODUCT_UPDATE = """
mutation($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id seo { title description } }
    userErrors { field message }
  }
}
"""

COLLECTION_UPDATE = """
mutation($input: CollectionInput!) {
  collectionUpdate(input: $input) {
    collection { id seo { title description } }
    userErrors { field message }
  }
}
"""

PAGE_UPDATE = """
mutation($input: PageInput!) {
  pageUpdate(input: $input) {
    page { id seo { title description } }
    userErrors { field message }
  }
}
"""

ARTICLE_UPDATE = """
mutation($id: ID!, $input: ArticleUpdateInput!) {
  articleUpdate(id: $id, input: $input) {
    article { id seo { title description } }
    userErrors { field message }
  }
}
"""


def fetch_all_paginated(query, root_key, store=None, token=None, variables=None):
    """Récupère toutes les pages d'une query paginée."""
    all_items = []
    cursor = None
    while True:
        vars_ = {"cursor": cursor}
        if variables:
            vars_.update(variables)
        data = graphql_request(query, vars_, store, token)
        root = data[root_key]
        # Gestion blogs > articles (nested)
        if isinstance(root, dict) and "articles" in root:
            root = root["articles"]
        edges = root["edges"]
        page_info = root["pageInfo"]
        for edge in edges:
            all_items.append(edge["node"])
        if not page_info["hasNextPage"]:
            break
        cursor = page_info["endCursor"]
    return all_items


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file("shopify-seo-tool.html")


@app.route("/api/resources")
def get_resources():
    """Récupère les ressources Shopify avec leurs données SEO."""
    store = request.args.get("store", SHOPIFY_STORE)
    token = request.args.get("token", SHOPIFY_ACCESS_TOKEN)
    resource_type = request.args.get("type", "all")

    if not store or not token:
        return jsonify({"error": "Store et access token requis"}), 400

    results = []

    try:
        # Produits
        if resource_type in ("all", "products"):
            products = fetch_all_paginated(PRODUCTS_QUERY, "products", store, token)
            for p in products:
                results.append({
                    "id": p["id"],
                    "type": "product",
                    "title": p["title"],
                    "handle": p["handle"],
                    "status": p.get("status", ""),
                    "meta_title": (p.get("seo") or {}).get("title") or "",
                    "meta_description": (p.get("seo") or {}).get("description") or "",
                })

        # Collections
        if resource_type in ("all", "collections"):
            collections = fetch_all_paginated(COLLECTIONS_QUERY, "collections", store, token)
            for c in collections:
                results.append({
                    "id": c["id"],
                    "type": "collection",
                    "title": c["title"],
                    "handle": c["handle"],
                    "status": "",
                    "meta_title": (c.get("seo") or {}).get("title") or "",
                    "meta_description": (c.get("seo") or {}).get("description") or "",
                })

        # Pages
        if resource_type in ("all", "pages"):
            pages = fetch_all_paginated(PAGES_QUERY, "pages", store, token)
            for pg in pages:
                results.append({
                    "id": pg["id"],
                    "type": "page",
                    "title": pg["title"],
                    "handle": pg["handle"],
                    "status": "",
                    "meta_title": (pg.get("seo") or {}).get("title") or "",
                    "meta_description": (pg.get("seo") or {}).get("description") or "",
                })

        # Articles de blog
        if resource_type in ("all", "articles"):
            blogs = fetch_all_paginated(BLOGS_QUERY, "blogs", store, token, {})
            # blogs query is not paginated the same way, let's handle it
            blogs_data = graphql_request(BLOGS_QUERY, {}, store, token)
            for blog_edge in blogs_data["blogs"]["edges"]:
                blog = blog_edge["node"]
                articles = fetch_all_paginated(
                    ARTICLES_QUERY, "blog", store, token,
                    {"blogId": blog["id"]}
                )
                for a in articles:
                    results.append({
                        "id": a["id"],
                        "type": "article",
                        "title": a["title"],
                        "handle": a["handle"],
                        "status": "",
                        "blog_title": blog["title"],
                        "meta_title": (a.get("seo") or {}).get("title") or "",
                        "meta_description": (a.get("seo") or {}).get("description") or "",
                    })

        return jsonify({"resources": results, "count": len(results)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/update", methods=["POST"])
def update_resources():
    """Met à jour en masse les meta titles/descriptions."""
    data = request.json
    store = data.get("store", SHOPIFY_STORE)
    token = data.get("token", SHOPIFY_ACCESS_TOKEN)
    updates = data.get("updates", [])

    if not store or not token:
        return jsonify({"error": "Store et access token requis"}), 400
    if not updates:
        return jsonify({"error": "Aucune mise à jour fournie"}), 400

    results = []

    for item in updates:
        resource_id = item["id"]
        resource_type = item["type"]
        meta_title = item.get("meta_title", "")
        meta_description = item.get("meta_description", "")

        try:
            if resource_type == "product":
                resp = graphql_request(PRODUCT_UPDATE, {
                    "input": {
                        "id": resource_id,
                        "seo": {"title": meta_title, "description": meta_description}
                    }
                }, store, token)
                errors = resp["productUpdate"]["userErrors"]

            elif resource_type == "collection":
                resp = graphql_request(COLLECTION_UPDATE, {
                    "input": {
                        "id": resource_id,
                        "seo": {"title": meta_title, "description": meta_description}
                    }
                }, store, token)
                errors = resp["collectionUpdate"]["userErrors"]

            elif resource_type == "page":
                resp = graphql_request(PAGE_UPDATE, {
                    "input": {
                        "id": resource_id,
                        "seo": {"title": meta_title, "description": meta_description}
                    }
                }, store, token)
                errors = resp["pageUpdate"]["userErrors"]

            elif resource_type == "article":
                resp = graphql_request(ARTICLE_UPDATE, {
                    "id": resource_id,
                    "input": {
                        "seo": {"title": meta_title, "description": meta_description}
                    }
                }, store, token)
                errors = resp["articleUpdate"]["userErrors"]

            else:
                results.append({"id": resource_id, "status": "error", "message": f"Type inconnu: {resource_type}"})
                continue

            if errors:
                results.append({
                    "id": resource_id,
                    "status": "error",
                    "message": "; ".join(e["message"] for e in errors)
                })
            else:
                results.append({"id": resource_id, "status": "success"})

        except Exception as e:
            results.append({"id": resource_id, "status": "error", "message": str(e)})

        # Pause pour respecter les rate limits Shopify
        time.sleep(0.5)

    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] == "error")

    return jsonify({
        "results": results,
        "summary": {
            "total": len(results),
            "success": success_count,
            "errors": error_count
        }
    })


if __name__ == "__main__":
    print("=" * 60)
    print("  Shopify SEO Tool - Mise à jour en masse")
    print("  http://localhost:5000")
    print("=" * 60)
    app.run(debug=True, port=5000)
