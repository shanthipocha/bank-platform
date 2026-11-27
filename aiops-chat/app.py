import json, os, re
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import common
from llm import explain

NS = "default"
SERVICES = ["frontend", "userservice", "contacts", "balancereader", "ledgerwriter",
            "transactionhistory", "accounts-db", "ledger-db", "loadgenerator"]
HELP = ("Ask me about a bank service, e.g. `@alertmanager why is balancereader restarting?` "
        "I know: " + ", ".join(SERVICES) + ". I only read; I never change anything.")

app = App(token=os.environ["SLACK_BOT_TOKEN"])

def norm(s):
    return re.sub(r"[^a-z]", "", s.lower())

def find_service(text):
    n = norm(text)
    for s in SERVICES:
        if norm(s) in n:
            return s
    return None

def build_context(service):
    lines = []
    if service:
        pods = common.pods_for(NS, service)
        if not pods:
            lines.append(f"No pods exist for {service} (scaled to 0 or deleted?).")
        for p in pods[:2]:
            lines += common.pod_summary(p)
        if pods:
            name = pods[0]["metadata"]["name"]
            ev = common.events(NS, name)
            if ev:
                lines.append("Events:\n" + "\n".join(ev))
            lines.append("Recent logs:\n" + common.logs(NS, name))
    else:
        items = json.loads(common.k8s(f"/api/v1/namespaces/{NS}/pods"))["items"]
        for p in items[:12]:
            lines += common.pod_summary(p)
    try:
        lines.append("Cross-service errors (Loki):\n" + common.loki_errors(NS))
    except Exception as e:
        lines.append(f"(Loki not available: {e})")
    return "\n".join(lines)[:3500]

@app.event("app_mention")
def on_mention(event, say):
    ts = event.get("thread_ts") or event["ts"]
    text = re.sub(r"<@[^>]+>", "", event.get("text", "")).strip()
    if not text:
        say(text=HELP, thread_ts=ts)
        return
    service = find_service(text)
    try:
        ctx = build_context(service)
        ai = explain(f"Question: {text}\n\nContext:\n{ctx}")
    except Exception as e:
        say(text=f"Sorry, I could not collect context: {e}", thread_ts=ts)
        return
    body = f"*Context{' for ' + service if service else ' (all pods)'}*\n```{ctx[:1800]}```"
    body += ("\n*AI analysis:*\n" + ai[:1500]) if ai else "\n_LLM is off, showing context only._"
    say(text=body, thread_ts=ts)

@app.event("message")
def ignore_messages():
    pass

if __name__ == "__main__":
    print("aiops-chat starting (Socket Mode)", flush=True)
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
