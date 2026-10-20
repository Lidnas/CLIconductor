from collections import defaultdict, deque


def detect_cycle(tasks):
    # tasks: dict id -> list of dependency ids
    indeg = {n: 0 for n in tasks}
    adj = defaultdict(list)
    for n, deps in tasks.items():
        for d in deps:
            if d not in tasks:
                continue
            adj[d].append(n)
            indeg[n] += 1
    # Kahn
    q = deque([n for n in tasks if indeg[n] == 0])
    seen = 0
    while q:
        u = q.popleft()
        seen += 1
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if seen != len(tasks):
        # find cycle
        return True, _find_cycle(tasks)
    return False, None


def _find_cycle(tasks):
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in tasks}
    parent = {}
    cycle = []

    def dfs(u):
        color[u] = GRAY
        for d in tasks.get(u, []):
            if d not in tasks:
                continue
            if color.get(d, WHITE) == WHITE:
                parent[d] = u
                res = dfs(d)
                if res:
                    return res
            elif color.get(d, WHITE) == GRAY:
                # found cycle d..u
                cur = u
                cycle.append(d)
                while cur != d and cur is not None:
                    cycle.append(cur)
                    cur = parent.get(cur)
                cycle.reverse()
                return cycle
        color[u] = BLACK
        return None

    for n in tasks:
        if color[n] == WHITE:
            parent[n] = None
            res = dfs(n)
            if res:
                return res
    return None


def topological_order(tasks):
    # returns list of ids in topo order, or None if cycle
    cycle, _ = detect_cycle(tasks) if False else (None, None)
    is_cycle, _ = detect_cycle(tasks)
    if is_cycle:
        return None
    indeg = {n: 0 for n in tasks}
    adj = defaultdict(list)
    for n, deps in tasks.items():
        for d in deps:
            if d in tasks:
                adj[d].append(n)
                indeg[n] += 1
    q = deque(sorted(n for n in tasks if indeg[n] == 0))
    out = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in sorted(adj[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    return out


def ready_tasks(tasks, done_ids):
    # tasks: dict id->Task-like with .dependencies and .state
    out = []
    for tid, t in tasks.items():
        if getattr(t, "state", None) not in ("pending", "ready"):
            continue
        deps = getattr(t, "dependencies", []) or []
        if all(d in done_ids for d in deps):
            out.append(tid)
    return out