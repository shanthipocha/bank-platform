import json, os, urllib.request

SYSTEM = ("You are an SRE assistant for Bank of Anthos running on Kubernetes. "
          "Given alert context, reply in at most 6 short lines: likely cause, the evidence "
          "from the context, and 2-3 read-only next steps (kubectl commands). If several pods "
          "restarted at the same time, suspect a node or Docker restart rather than the app. "
          "A startup probe failure for a Java service is normal during its first ~60s of boot, so do not call it a root cause unless it persists. If one service has errors from many callers, treat that service as the likely root cause and the callers as victims. Keep the whole reply under 900 characters. Each pod line shows its age: a very young pod (a few minutes) with restarts=0 was recently recreated, so look at it first. In this app, 'Cache error' or SQLState 08001 in balancereader, transactionhistory or ledgerwriter means the ledger database was unreachable. Frontend 'insufficient balance' errors are normal business errors, not faults. Prefer the explanation that fits the pod ages and the order of events. Never suggest deleting data. Say 'unsure' if the evidence is thin.")

def _post(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def explain(context):
    provider = os.environ.get("LLM_PROVIDER", "none")
    if provider == "none":
        return ""
    model = os.environ.get("LLM_MODEL", "")
    key = os.environ.get("LLM_API_KEY", "")
    context = context[:3000]
    try:
        if provider == "anthropic":
            r = _post("https://api.anthropic.com/v1/messages",
                      {"x-api-key": key, "anthropic-version": "2023-06-01"},
                      {"model": model, "max_tokens": 1200, "system": SYSTEM,
                       "messages": [{"role": "user", "content": context}]})
            return r["content"][0]["text"].strip()
        if provider == "openai":  # Ollama, Gemini, Groq, any OpenAI-compatible API
            base = os.environ["LLM_BASE_URL"].rstrip("/")
            r = _post(base + "/chat/completions", {"Authorization": "Bearer " + key},
                      {"model": model, "max_tokens": 2000, "reasoning_effort": "low",
                       "messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": context}]})
            return r["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("LLM call failed:", e, flush=True)
    return ""
