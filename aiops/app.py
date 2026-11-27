import json, os, ssl, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from llm import explain

API = "https://kubernetes.default.svc"
SA = "/var/run/secrets/kubernetes.io/serviceaccount"
CTX = ssl.create_default_context(cafile=f"{SA}/ca.crt")
SEEN = {}  # fingerprint -> last handled time (dedupe)

HINTS = {
    "BankDatabaseDown": "Check the StatefulSet replicas (scaled to 0?), PVC status, and the DB pod events/logs.",
    "BankPodCrashLooping": "Read the previous container logs and the last exit reason. Common causes: bad config or Secret, DB unreachable, OOMKilled.",
    "BankServiceUnavailable": "Check rollout status, readiness probe failures, and whether the DB this service depends on is healthy.",
    "BankHighRestartRate": "Look at lastExit reason (OOMKilled, Error) and whether a dependency such as the DB restarted first.",
}

def k8s(path):
    token = open(f"{SA}/token").read()
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, context=CTX, timeout=10) as r:
        return r.read().decode()

def pods_for(ns, target):
    items = json.loads(k8s(f"/api/v1/namespaces/{ns}/pods"))["items"]
    return [p for p in items
            if p["metadata"]["name"] == target or p["metadata"]["name"].startswith(target + "-")]

def pod_summary(p):
    name = p["metadata"]["name"]
    statuses = p["status"].get("containerStatuses", [])
    if not statuses:
        return [f"{name}: phase={p['status'].get('phase')} (no container status yet)"]
    out = []
    for c in statuses:
        state = next(iter(c["state"]))
        reason = c["state"][state].get("reason", "")
        last = c.get("lastState", {}).get("terminated", {}).get("reason", "-")
        out.append(f"{name}/{c['name']}: {state} {reason} ready={c['ready']} restarts={c['restartCount']} lastExit={last}")
    return out

def events(ns, name):
    q = urllib.parse.quote(f"involvedObject.name={name}")
    items = json.loads(k8s(f"/api/v1/namespaces/{ns}/events?fieldSelector={q}"))["items"]
    items.sort(key=lambda e: e.get("lastTimestamp") or e["metadata"]["creationTimestamp"])
    return [f"{e['reason']}: {e['message']}"[:200] for e in items[-4:]]

def logs(ns, name):
    for suffix in ("", "&previous=true"):
        try:
            return k8s(f"/api/v1/namespaces/{ns}/pods/{name}/log?tailLines=12{suffix}")[-1200:]
        except Exception:
            continue
    return "(no logs available)"


LOKI = os.environ.get("LOKI_URL", "http://loki.monitoring.svc:3100")

def loki_errors(ns):
    q = urllib.parse.urlencode({
        "query": '{namespace="%s"} |~ "(?i)error|exception|refused|timed out"' % ns,
        "since": "10m", "limit": "200", "direction": "backward"})
    with urllib.request.urlopen(f"{LOKI}/loki/api/v1/query_range?{q}", timeout=10) as r:
        streams = json.loads(r.read().decode())["data"]["result"]
    counts, samples = {}, {}
    for st in streams:
        app = st["stream"].get("app", st["stream"].get("pod", "?"))
        for _, line in st["values"]:
            counts[app] = counts.get(app, 0) + 1
            samples.setdefault(app, line[:160])
    if not counts:
        return "No error lines in Loki for the last 10 minutes."
    out = ["Errors in the last 10 min (per service): " +
           ", ".join(f"{a}={n}" for a, n in sorted(counts.items(), key=lambda x: -x[1]))]
    out += [f"- {a}: {samples[a]}" for a in list(counts)[:4]]
    return "\n".join(out)

def analyse(alert):
    l, a = alert["labels"], alert.get("annotations", {})
    ns = l.get("namespace", "default")
    target = l.get("statefulset") or l.get("deployment") or l.get("pod")
    lines = [f"*AIOps context: {l.get('alertname')}*", a.get("summary", ""), a.get("description", "")]
    if ns != "default" or not target:
        lines.append("_Outside the default namespace or no target found; no context collected._")
    else:
        try:
            pods = pods_for(ns, target)
            if not pods:
                lines.append(f"No pods exist for `{target}`. It may be scaled to 0 or deleted: `kubectl get sts,deploy {target}`")
            for p in pods[:2]:
                lines += ["```" + "\n".join(pod_summary(p)) + "```"]
                ev = events(ns, p["metadata"]["name"])
                if ev:
                    lines.append("Events:\n```" + "\n".join(ev) + "```")
                lines.append("Recent logs:\n```" + logs(ns, p["metadata"]["name"]) + "```")
        except Exception as e:
            lines.append(f"_Context collection failed: {e}_")
    try:
        lines.append("Cross-service errors (Loki):\n```" + loki_errors(ns) + "```")
    except Exception as e:
        lines.append(f"_Loki query failed: {e}_")
    lines.append("*Hint:* " + HINTS.get(l.get("alertname"), "No runbook hint for this alert yet."))
    text = "\n".join(x for x in lines if x)[:2200]
    ai = explain(text)
    return text + ("\n\n*AI analysis:*\n" + ai[:1500] if ai else "")

def post_slack(severity, text):
    url = os.environ["CRIT_URL"] if severity == "critical" else os.environ["WARN_URL"]
    req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).read()

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        for al in data.get("alerts", []):
            fp = al.get("fingerprint", al["labels"].get("alertname"))
            if al.get("status") != "firing" or time.time() - SEEN.get(fp, 0) < 3600:
                continue
            SEEN[fp] = time.time()
            post_slack(al["labels"].get("severity", "warning"), analyse(al))
        self.send_response(200); self.end_headers(); self.wfile.write(b"done")

HTTPServer(("", 8080), H).serve_forever()
