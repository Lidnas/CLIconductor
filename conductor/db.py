import sqlite3
import json
import time
import os
import threading
from typing import Any, Optional, List, Dict


class Store:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        c = self.conn
        c.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            objective TEXT,
            state TEXT,
            created_at REAL,
            base_commit TEXT,
            integration_branch TEXT,
            budget TEXT,
            criteria TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            run_id TEXT,
            objective TEXT,
            state TEXT,
            role TEXT,
            assignee TEXT,
            dependencies TEXT,
            lease_id TEXT,
            fencing_token INTEGER,
            attempts INTEGER,
            max_attempts INTEGER,
            priority INTEGER,
            metadata TEXT,
            created_at REAL,
            updated_at REAL,
            result TEXT,
            failure_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY,
            run_id TEXT,
            cli TEXT,
            role TEXT,
            instance INTEGER,
            state TEXT,
            token TEXT,
            workspace TEXT,
            branch TEXT,
            process_pid INTEGER,
            session_id TEXT,
            last_progress REAL,
            capabilities TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            run_id TEXT,
            correlation_id TEXT,
            task_id TEXT,
            sender TEXT,
            recipient TEXT,
            type TEXT,
            timestamp REAL,
            payload TEXT,
            status TEXT,
            attempts INTEGER,
            idempotency_key TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT,
            task_id TEXT,
            agent_id TEXT,
            type TEXT,
            actor TEXT,
            reason TEXT,
            timestamp REAL,
            payload TEXT
        );
        CREATE TABLE IF NOT EXISTS leases (
            lease_id TEXT PRIMARY KEY,
            task_id TEXT,
            agent_id TEXT,
            fencing_token INTEGER,
            acquired_at REAL,
            expires_at REAL,
            heartbeat_at REAL
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
            run_id TEXT PRIMARY KEY,
            state TEXT,
            updated_at REAL
        );
        """)
        self.conn.commit()

    def _j(self, v):
        return json.dumps(v) if v is not None else None

    def _rj(self, v):
        return json.loads(v) if v else None

    # Runs
    def save_run(self, run):
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO runs(run_id,objective,state,created_at,base_commit,integration_branch,budget,criteria) VALUES (?,?,?,?,?,?,?,?)",
                (run.run_id, run.objective, run.state, run.created_at, run.base_commit, run.integration_branch, self._j(run.budget), self._j([c.__dict__ if hasattr(c,'__dict__') else c for c in run.criteria])),
            )
            self.conn.commit()

    def load_run(self, run_id):
        r = self.conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def list_runs(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()]

    # Tasks
    def save_task(self, task, run_id=None):
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO tasks(task_id,run_id,objective,state,role,assignee,dependencies,lease_id,fencing_token,attempts,max_attempts,priority,metadata,created_at,updated_at,result,failure_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task.task_id, run_id, task.objective, task.state, task.role, task.assignee,
                 self._j(task.dependencies), task.lease_id, task.fencing_token, task.attempts,
                 task.max_attempts, task.priority, self._j(task.metadata), task.created_at,
                 task.updated_at, self._j(task.result), task.failure_reason),
            )
            self.conn.commit()

    def load_task(self, task_id):
        r = self.conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["dependencies"] = self._rj(d["dependencies"]) or []
        d["metadata"] = self._rj(d["metadata"]) or {}
        d["result"] = self._rj(d["result"])
        return d

    def list_tasks(self, run_id=None):
        q = "SELECT * FROM tasks"
        args = ()
        if run_id:
            q += " WHERE run_id=?"
            args = (run_id,)
        rows = self.conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["dependencies"] = self._rj(d["dependencies"]) or []
            d["metadata"] = self._rj(d["metadata"]) or {}
            d["result"] = self._rj(d["result"])
            out.append(d)
        return out

    def delete_task(self, task_id):
        with self._lock:
            self.conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            self.conn.commit()

    # Agents
    def save_agent(self, agent, run_id=None):
        with self._lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO agents(agent_id,run_id,cli,role,instance,state,token,workspace,branch,process_pid,session_id,last_progress,capabilities)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (agent.agent_id, run_id, agent.cli, agent.role, agent.instance, agent.state, agent.token,
                 agent.workspace, agent.branch, agent.process_pid, agent.session_id, agent.last_progress,
                 self._j(agent.capabilities)),
            )
            self.conn.commit()

    def load_agent_by_token(self, token):
        r = self.conn.execute("SELECT * FROM agents WHERE token=?", (token,)).fetchone()
        return dict(r) if r else None

    def list_agents(self, run_id=None):
        q = "SELECT * FROM agents"
        args = ()
        if run_id:
            q += " WHERE run_id=?"
            args = (run_id,)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    # Messages
    def save_message(self, msg, run_id=None):
        with self._lock:
            try:
                self.conn.execute(
                    """INSERT INTO messages(message_id,run_id,correlation_id,task_id,sender,recipient,type,timestamp,payload,status,attempts,idempotency_key)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (msg.message_id, run_id, msg.correlation_id, msg.task_id, msg.sender, msg.recipient,
                     msg.type, msg.timestamp, self._j(msg.payload), msg.status, msg.attempts, msg.idempotency_key),
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # duplicate idempotency

    def update_message_status(self, message_id, status, attempts=None):
        with self._lock:
            if attempts is None:
                self.conn.execute("UPDATE messages SET status=? WHERE message_id=?", (status, message_id))
            else:
                self.conn.execute("UPDATE messages SET status=?, attempts=? WHERE message_id=?", (status, attempts, message_id))
            self.conn.commit()

    def list_messages(self, run_id=None, recipient=None, status=None):
        q = "SELECT * FROM messages WHERE 1=1"
        args = []
        if run_id:
            q += " AND run_id=?"; args.append(run_id)
        if recipient:
            q += " AND recipient=?"; args.append(recipient)
        if status:
            q += " AND status=?"; args.append(status)
        q += " ORDER BY timestamp"
        rows = self.conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = self._rj(d["payload"])
            out.append(d)
        return out

    # Events
    def append_event(self, ev, run_id=None):
        with self._lock:
            self.conn.execute(
                """INSERT INTO events(event_id,run_id,task_id,agent_id,type,actor,reason,timestamp,payload)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (ev.event_id, run_id or ev.run_id, ev.task_id, ev.agent_id, ev.type, ev.actor, ev.reason, ev.timestamp, self._j(ev.payload)),
            )
            self.conn.commit()

    def list_events(self, run_id=None, limit=500):
        q = "SELECT * FROM events"
        args = ()
        if run_id:
            q += " WHERE run_id=?"; args = (run_id,)
        q += " ORDER BY timestamp DESC LIMIT ?"
        args = args + (limit,)
        rows = self.conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = self._rj(d["payload"])
            out.append(d)
        return out

    # Leases
    def save_lease(self, lease):
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO leases(lease_id,task_id,agent_id,fencing_token,acquired_at,expires_at,heartbeat_at) VALUES (?,?,?,?,?,?,?)",
                (lease.lease_id, lease.task_id, lease.agent_id, lease.fencing_token, lease.acquired_at, lease.expires_at, lease.heartbeat_at),
            )
            self.conn.commit()

    def load_lease(self, task_id):
        r = self.conn.execute("SELECT * FROM leases WHERE task_id=?", (task_id,)).fetchone()
        return dict(r) if r else None

    def delete_lease(self, task_id):
        with self._lock:
            self.conn.execute("DELETE FROM leases WHERE task_id=?", (task_id,))
            self.conn.commit()

    # Checkpoint
    def save_checkpoint(self, run_id, state):
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO checkpoints(run_id,state,updated_at) VALUES (?,?,?)",
                              (run_id, self._j(state), time.time()))
            self.conn.commit()

    def load_checkpoint(self, run_id):
        r = self.conn.execute("SELECT state FROM checkpoints WHERE run_id=?", (run_id,)).fetchone()
        return self._rj(r["state"]) if r else None

    def close(self):
        self.conn.close()