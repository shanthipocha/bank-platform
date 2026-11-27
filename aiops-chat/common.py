import json, os, ssl, time, urllib.parse, urllib.request

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

