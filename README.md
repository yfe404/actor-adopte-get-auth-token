# Adopte.app Login → Token Extractor

This Apify Actor logs into **[adopte.app](https://www.adopte.app)** with your
credentials, captures the **`apiRefreshToken`** that the web app places on
`window`, then exchanges it for an **Auth Token** via
`POST /api/v4/authtokens`.  
All traffic goes through an Apify **Residential FR** proxy so it looks like a
legit French user session.


## Input

| key | type | required | default | description |
|-----|------|----------|---------|-------------|
| `email` | string | ✅ | — | Adopte account email |
| `password` | string (secret) | ✅ | — | Account password |
| `headless` | boolean | ❌ | `true` | Run browser UI if you need to debug |
| `proxyConfiguration` | object | ❌ | Apify default | Override proxy group / country |

The complete JSON schema lives in **`input_schema.json`**.


## Output (dataset item)

```json
{
  "success": true,
  "apiRefreshToken": "eyJ2ZXJzaW9uIjoxLCJ0eXAiOiJKV1Qi…",
  "authToken": "eyJ2ZXJzaW9uIjoxLCJ0eXAiOiJKV1Qi…",
  "authtokensStatus": 200
}
````

`authtokensStatus == 200` confirms the Auth Token is valid.


## Code style

The repo ships with **pre-commit** hooks that run

* `ruff-format`  – opinionated formatter + import sorter
* `ruff --fix`   – fast linter with autofix
* `black`        – final style safety net

Run once on the whole repo:

```bash
pre-commit run --all-files
```

Happy hacking 🚀
