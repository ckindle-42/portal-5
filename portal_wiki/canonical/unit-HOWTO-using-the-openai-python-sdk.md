---
id: unit-HOWTO-using-the-openai-python-sdk
kind: why
title: "HOWTO \u2014 Using the OpenAI Python SDK"
sources:
- type: design
  path: docs/HOWTO.md
  section: Using the OpenAI Python SDK
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.862161
updated_at: 1783195000.862161
---


```python
from openai import OpenAI
import os

client = OpenAI(
    base_url="http://localhost:9099/v1",
    api_key=os.environ["PIPELINE_API_KEY"],
)

response = client.chat.completions.create(
    model="auto-security",
    messages=[{"role": "user", "content": "Review this nginx config for security issues:\nserver { listen 80; root /var/www; }"}],
)
print(response.choices[0].message.content)
```
