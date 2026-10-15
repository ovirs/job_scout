"""Print the HTTP API's OpenAPI schema, from which the frontend's client is generated."""

import json

from job_scout.api import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=2))
