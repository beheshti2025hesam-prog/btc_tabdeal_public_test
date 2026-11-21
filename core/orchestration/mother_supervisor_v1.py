from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import multiprocessing, pickle, threading, time
from typing import Any, Callable

@dataclass(frozen=True)
class SupervisionResultV1:
    agent: str
    request_id: str
    status: str
    attempts: int
    duration_ms: float
    value: Any = None
    reason_code: str = ""
    def as_dict(self) -> dict[str, Any]:
        return {"agent":self.agent,"request_id":self.request_id,"status":self.status,
                "attempts":self.attempts,"duration_ms":self.duration_ms,"reason_code":self.reason_code}

def _child_invoke(send_conn: Any, fn: Callable[..., Any], args: tuple[Any,...], kwargs: dict[str,Any]) -> None:
    try: send_conn.send((True, fn(*args, **kwargs)))
    except BaseException as exc:
        try: send_conn.send((False,(type(exc).__name__,str(exc)[:256])))
        except BaseException: pass
    finally: send_conn.close()

class SpecialistSupervisorV1:
    """Bounded process-isolated supervisor. No trading or journal capabilities."""
    VERSION="hes-specialist-supervisor-v1"
    def __init__(self, *, failure_threshold:int=2, cache_size:int=2048, kill_grace_seconds:float=0.25,
                 max_concurrent_per_agent:int=1):
        if (isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int) or failure_threshold < 1
                or isinstance(cache_size, bool) or not isinstance(cache_size, int) or cache_size < 1
                or isinstance(kill_grace_seconds, bool) or not isinstance(kill_grace_seconds, (int, float))
                or kill_grace_seconds <= 0
                or isinstance(max_concurrent_per_agent, bool)
                or not isinstance(max_concurrent_per_agent, int) or max_concurrent_per_agent < 1):
            raise ValueError("invalid supervisor limits")
        self.failure_threshold=failure_threshold; self.cache_size=cache_size; self.kill_grace_seconds=kill_grace_seconds
        self.max_concurrent_per_agent=max_concurrent_per_agent
        self._lock=threading.RLock(); self._condition=threading.Condition(self._lock); self._cache=OrderedDict(); self._inflight=set(); self._active_agents=set(); self._active_counts={}; self._failures={}
    @staticmethod
    def _validate(agent, request_id, timeout_seconds):
        if not isinstance(agent,str) or not agent.strip() or len(agent)>128: raise ValueError("agent name is required")
        if not isinstance(request_id,str) or not request_id.strip() or len(request_id)>256: raise ValueError("request_id is required")
        if isinstance(timeout_seconds,bool) or not isinstance(timeout_seconds,(int,float)): raise ValueError("timeout_seconds must be numeric")
        if not 0<float(timeout_seconds)<=120: raise ValueError("timeout_seconds must be in (0, 120]")
    def _invoke_once(self,fn,args,kwargs,timeout):
        try:
            pickle.dumps((fn,args,kwargs))
        except Exception as exc:
            return "FAILED", ("SPECIALIST_NOT_SERIALIZABLE", type(exc).__name__), 0.0
        ctx=multiprocessing.get_context("spawn"); recv_conn,send_conn=ctx.Pipe(duplex=False)
        process=ctx.Process(target=_child_invoke,args=(send_conn,fn,args,kwargs),daemon=True); started=time.monotonic()
        try:
            try:
                process.start()
            except Exception as exc:
                return "FAILED", ("SPECIALIST_PROCESS_START_FAILED", type(exc).__name__), (time.monotonic()-started)*1000
            send_conn.close()
            if recv_conn.poll(timeout):
                try: ok,payload=recv_conn.recv()
                except (EOFError,OSError): ok,payload=False,("CHILD_EXITED","child exited without a result")
                process.join(self.kill_grace_seconds)
                if process.is_alive(): process.terminate(); process.join(self.kill_grace_seconds)
                if process.is_alive() and hasattr(process,"kill"): process.kill(); process.join(self.kill_grace_seconds)
                if ok: return "SUCCEEDED",payload,(time.monotonic()-started)*1000
                kind,detail=payload if isinstance(payload,tuple) and len(payload)==2 else ("CHILD_ERROR","invalid child error")
                return "FAILED",(kind,detail),(time.monotonic()-started)*1000
            process.terminate(); process.join(self.kill_grace_seconds)
            if process.is_alive() and hasattr(process,"kill"): process.kill(); process.join(self.kill_grace_seconds)
            return "TIMEOUT",None,(time.monotonic()-started)*1000
        finally:
            try: send_conn.close()
            except OSError: pass
            recv_conn.close()
            if process.pid is not None and process.is_alive():
                process.kill() if hasattr(process,"kill") else process.terminate()
                process.join(self.kill_grace_seconds)
            process.close()
    def execute(self,agent,request_id,fn,*args,timeout_seconds=2.0,retry_safe=False,**kwargs):
        self._validate(agent,request_id,timeout_seconds)
        if not callable(fn): raise ValueError("specialist callable is required")
        if not isinstance(retry_safe,bool): raise ValueError("retry_safe must be boolean")
        key=(agent,request_id)
        with self._condition:
            cached=self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return SupervisionResultV1(agent,request_id,"DUPLICATE",0,0.0,cached.value,"IDEMPOTENT_REPLAY:"+cached.status)
            if key in self._inflight:
                # Same evidence/request callers share the bounded in-flight work.
                # A different request for this specialist remains BUSY (no queue).
                wait_budget=float(timeout_seconds)*(2 if retry_safe else 1)+self.kill_grace_seconds+0.5
                deadline=time.monotonic()+wait_budget
                while key in self._inflight:
                    remaining=deadline-time.monotonic()
                    if remaining<=0: break
                    self._condition.wait(timeout=min(0.1,remaining))
                cached=self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    return SupervisionResultV1(agent,request_id,"DUPLICATE",0,0.0,cached.value,"IDEMPOTENT_REPLAY:"+cached.status)
                return SupervisionResultV1(agent,request_id,"IN_PROGRESS",0,0.0,None,"REQUEST_RESULT_NOT_READY")
            if self._active_counts.get(agent, 0) >= self.max_concurrent_per_agent:
                return SupervisionResultV1(agent,request_id,"BUSY",0,0.0,None,"SPECIALIST_CONCURRENCY_LIMIT")
            if self._failures.get(agent,0)>=self.failure_threshold:
                return SupervisionResultV1(agent,request_id,"CIRCUIT_OPEN",0,0.0,None,"SPECIALIST_CIRCUIT_OPEN")
            self._inflight.add(key); self._active_agents.add(agent)
            self._active_counts[agent] = self._active_counts.get(agent, 0) + 1
        started=time.monotonic(); attempts=0; final_status="FAILED"; value=None; reason="SPECIALIST_FAILED"
        try:
            max_attempts=2 if retry_safe else 1
            for attempts in range(1,max_attempts+1):
                status,payload,_=self._invoke_once(fn,args,kwargs,float(timeout_seconds))
                if status=="SUCCEEDED": final_status,value,reason="SUCCEEDED",payload,""; break
                if status=="TIMEOUT": reason="SPECIALIST_TIMEOUT"
                else:
                    kind,_detail=payload; reason="SPECIALIST_EXCEPTION:"+str(kind)[:64]
                final_status=status
                if attempts>=max_attempts: break
            result=SupervisionResultV1(agent,request_id,final_status,attempts,(time.monotonic()-started)*1000,value,reason)
            with self._lock:
                self._failures[agent]=0 if final_status=="SUCCEEDED" else self._failures.get(agent,0)+1
                self._cache[key]=result; self._cache.move_to_end(key)
                while len(self._cache)>self.cache_size: self._cache.popitem(last=False)
            return result
        finally:
            with self._condition:
                self._inflight.discard(key)
                remaining = self._active_counts.get(agent, 1) - 1
                if remaining <= 0:
                    self._active_counts.pop(agent, None)
                    self._active_agents.discard(agent)
                else:
                    self._active_counts[agent] = remaining
                self._condition.notify_all()
    def reset(self,agent):
        if not isinstance(agent,str) or not agent.strip(): raise ValueError("agent name is required")
        with self._lock:
            if self._active_counts.get(agent, 0) > 0:
                raise RuntimeError("cannot reset an active specialist")
            self._failures.pop(agent,None)
            # Explicit operator reset permits a controlled retry of failed work.
            # Successful request results remain cached to preserve idempotency.
            for key, result in list(self._cache.items()):
                if key[0] == agent and result.status != "SUCCEEDED":
                    self._cache.pop(key, None)
    def health(self):
        with self._lock:
            names=sorted(set(self._failures)|self._active_agents)
            return {"version":self.VERSION,"active_agents":sorted(self._active_agents),
                    "active_counts":dict(sorted(self._active_counts.items())),
                    "max_concurrent_per_agent":self.max_concurrent_per_agent,
                    "inflight_requests":len(self._inflight),
                    "agents":{n:{"consecutive_failures":self._failures.get(n,0),
                    "circuit":"OPEN" if self._failures.get(n,0)>=self.failure_threshold else "CLOSED"} for n in names},
                    "execution_authorized":False}

