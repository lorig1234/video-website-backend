from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone
import asyncio
import json
import uuid

router = APIRouter(tags=["Claude"])

_PASSWORD = "pierelol123"
_CLAUDE_BIN = "/home/tony-server/.vscode/extensions/anthropic.claude-code-2.1.114-linux-x64/resources/native-binary/claude"
_HISTORY_DIR = Path("/home/tony-server/pieres/video-website-backend/claude_history")
_HISTORY_DIR.mkdir(exist_ok=True)

# in-memory tracking of active runs: entry_id -> {prompt, session_id, started_at, pid}
_active_runs: dict = {}


def _format_tool_desc(name: str, inp: dict) -> str:
    if name == "Read":
        return f"Reading {inp.get('file_path', '?')}"
    if name == "Write":
        return f"Writing {inp.get('file_path', '?')}"
    if name == "Edit":
        return f"Editing {inp.get('file_path', '?')}"
    if name == "Bash":
        return f"Bash: {inp.get('command', '?')[:120]}"
    if name == "Glob":
        return f"Glob: {inp.get('pattern', '?')}"
    if name == "Grep":
        return f"Grep: {inp.get('pattern', '?')} in {inp.get('path', '.')}"
    if name == "WebSearch":
        return f"Search: {inp.get('query', '?')}"
    if name == "WebFetch":
        return f"Fetch: {inp.get('url', '?')}"
    return f"{name}: {str(inp)[:100]}"


_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Claude Code Runner</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #111; color: #e0e0e0; font-family: monospace; height: 100vh; display: flex; flex-direction: column; max-width: 960px; margin: 0 auto; padding: 20px; gap: 12px; }
        h1 { color: #a78bfa; font-size: 1.3rem; flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .hdr-btns { display: flex; gap: 8px; }
        .hdr-btn { padding: 6px 14px; background: #2a2a2a; color: #9ca3af; border: 1px solid #333; cursor: pointer; border-radius: 4px; font-size: 12px; font-family: monospace; }
        .hdr-btn:hover { background: #333; color: #e0e0e0; }
        #chat { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding: 4px 0; }
        .msg { display: flex; flex-direction: column; gap: 4px; }
        .msg-label { font-size: 11px; color: #4b5563; text-transform: uppercase; letter-spacing: 0.05em; }
        .msg-label.you { color: #7c3aed; }
        .msg-body { white-space: pre-wrap; line-height: 1.5; font-size: 13px; }
        .msg-body.you { color: #c4b5fd; }
        .msg-body.claude { color: #e0e0e0; }
        .tool-call { display: block; color: #4b5563; font-size: 11px; padding: 2px 0 2px 10px; border-left: 2px solid #1f2937; margin: 3px 0; font-family: monospace; }
        .divider { border: none; border-top: 1px solid #1f1f1f; }
        #inputArea { flex-shrink: 0; display: flex; flex-direction: column; gap: 8px; }
        textarea { width: 100%; height: 90px; background: #1e1e1e; color: #e0e0e0; border: 1px solid #333; padding: 10px; font-size: 13px; border-radius: 6px; resize: none; font-family: monospace; }
        textarea:focus { outline: none; border-color: #7c3aed; }
        .toolbar { display: flex; align-items: center; gap: 10px; }
        button#runBtn { padding: 8px 20px; background: #7c3aed; color: white; border: none; cursor: pointer; border-radius: 5px; font-size: 13px; font-family: monospace; }
        button#runBtn:hover:not(:disabled) { background: #6d28d9; }
        button#runBtn:disabled { background: #2a2a2a; color: #555; cursor: not-allowed; }
        .status { color: #6d28d9; font-size: 11px; }
        .hint { color: #374151; font-size: 11px; margin-left: auto; }
        /* Lock screen */
        #lock { position: fixed; inset: 0; background: #111; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; }
        #lock h2 { color: #a78bfa; font-size: 1.2rem; }
        #lock input { padding: 10px 14px; background: #1e1e1e; color: #e0e0e0; border: 1px solid #444; border-radius: 5px; font-size: 14px; font-family: monospace; width: 240px; text-align: center; }
        #lock input:focus { outline: none; border-color: #7c3aed; }
        #lock .err { color: #f87171; font-size: 12px; min-height: 16px; }
        /* Running modal */
        #runModal { position: fixed; inset: 0; background: rgba(0,0,0,0.85); display: none; z-index: 100; }
        #runPanel { position: absolute; right: 0; top: 0; bottom: 0; width: min(560px, 100vw); background: #161616; border-left: 1px solid #2a2a2a; display: flex; flex-direction: column; }
        #runHead { padding: 16px 20px; border-bottom: 1px solid #2a2a2a; display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; }
        #runHead h2 { color: #a78bfa; font-size: 1rem; }
        #runClose { background: none; border: none; color: #6b7280; cursor: pointer; font-size: 18px; font-family: monospace; }
        #runClose:hover { color: #e0e0e0; }
        #runList { flex: 1; overflow-y: auto; }
        .run-entry { padding: 14px 20px; border-bottom: 1px solid #1f1f1f; }
        .run-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #22c55e; margin-right: 6px; animation: pulse 1.5s ease-in-out infinite; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        .run-time { font-size: 10px; color: #4b5563; margin-bottom: 4px; }
        .run-prompt { font-size: 12px; color: #c4b5fd; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .run-pid { font-size: 10px; color: #374151; }
        .run-kill { margin-top: 6px; padding: 3px 10px; background: #2a0a0a; color: #f87171; border: 1px solid #450a0a; cursor: pointer; border-radius: 3px; font-size: 11px; font-family: monospace; }
        .run-kill:hover { background: #450a0a; }
        /* History modal */
        #histModal { position: fixed; inset: 0; background: rgba(0,0,0,0.85); display: none; z-index: 100; }
        #histPanel { position: absolute; right: 0; top: 0; bottom: 0; width: min(600px, 100vw); background: #161616; border-left: 1px solid #2a2a2a; display: flex; flex-direction: column; }
        #histHead { padding: 16px 20px; border-bottom: 1px solid #2a2a2a; display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; }
        #histHead h2 { color: #a78bfa; font-size: 1rem; }
        #histClose { background: none; border: none; color: #6b7280; cursor: pointer; font-size: 18px; font-family: monospace; }
        #histClose:hover { color: #e0e0e0; }
        #histList { flex: 1; overflow-y: auto; }
        .hist-entry { padding: 14px 20px; border-bottom: 1px solid #1f1f1f; cursor: pointer; }
        .hist-entry:hover { background: #1e1e1e; }
        .hist-time { font-size: 10px; color: #4b5563; margin-bottom: 4px; }
        .hist-prompt { font-size: 12px; color: #c4b5fd; margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .hist-preview { font-size: 11px; color: #6b7280; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .hist-entry.no-response .hist-preview { color: #7c2d12; }
        /* History detail view */
        #histDetail { position: absolute; inset: 0; background: #161616; display: none; flex-direction: column; }
        #histDetailHead { padding: 14px 20px; border-bottom: 1px solid #2a2a2a; display: flex; gap: 10px; align-items: center; flex-shrink: 0; }
        #histBack { background: none; border: none; color: #7c3aed; cursor: pointer; font-size: 13px; font-family: monospace; }
        #histDetailPrompt { font-size: 12px; color: #c4b5fd; flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
        #histCopyPrompt { padding: 3px 10px; background: #2a2a2a; color: #9ca3af; border: 1px solid #333; cursor: pointer; border-radius: 3px; font-size: 11px; font-family: monospace; flex-shrink: 0; }
        #histCopyPrompt:hover { background: #333; color: #e0e0e0; }
        #histDetailBody { flex: 1; overflow-y: auto; padding: 16px 20px; white-space: pre-wrap; font-size: 13px; line-height: 1.5; color: #e0e0e0; }
        #histDetailBody.no-response { color: #7c2d12; font-style: italic; }
    </style>
</head>
<body>
    <div id="lock">
        <h2>Claude Code Runner</h2>
        <input id="pw" type="password" placeholder="Password" autofocus />
        <button onclick="unlock()">Unlock</button>
        <span class="err" id="lockErr"></span>
    </div>

    <div id="app" style="display:none; flex: 1; flex-direction: column; gap: 12px; overflow: hidden;">
        <h1>Claude Code Runner
            <div class="hdr-btns">
                <button class="hdr-btn" onclick="openRunning()">Running</button>
                <button class="hdr-btn" onclick="openHistory()">History</button>
                <button class="hdr-btn" onclick="newChat()">+ New Chat</button>
            </div>
        </h1>
        <div id="chat"></div>
        <hr class="divider">
        <div id="inputArea">
            <textarea id="prompt" placeholder="Ask Claude anything..." rows="3"></textarea>
            <div class="toolbar">
                <button id="runBtn" onclick="run()">Send</button>
                <span class="status" id="status"></span>
                <span class="hint">Ctrl+Enter to send</span>
            </div>
        </div>
    </div>

    <!-- Running modal -->
    <div id="runModal">
        <div id="runPanel">
            <div id="runHead">
                <h2>Currently Running</h2>
                <button id="runClose" onclick="closeRunning()">&#x2715;</button>
            </div>
            <div id="runList"></div>
        </div>
    </div>

    <!-- History modal -->
    <div id="histModal">
        <div id="histPanel">
            <div id="histHead">
                <h2>History</h2>
                <button id="histClose" onclick="closeHistory()">&#x2715;</button>
            </div>
            <div id="histList"></div>
            <!-- Detail view -->
            <div id="histDetail">
                <div id="histDetailHead">
                    <button id="histBack" onclick="showHistList()">&#x2190; Back</button>
                    <div id="histDetailPrompt"></div>
                    <button id="histCopyPrompt" onclick="copyPrompt()">Copy prompt</button>
                </div>
                <div id="histDetailBody"></div>
            </div>
        </div>
    </div>

    <script>
        const SESSION_KEY = 'claude_pw';
        let pw = sessionStorage.getItem(SESSION_KEY) || '';
        let sessionId = null;
        let _currentDetailPrompt = '';

        function unlock() {
            pw = document.getElementById('pw').value;
            verifyAndShow();
        }

        function verifyAndShow() {
            if (pw !== 'pierelol123') {
                sessionStorage.removeItem(SESSION_KEY);
                pw = '';
                document.getElementById('lockErr').textContent = 'Wrong password.';
                document.getElementById('pw').value = '';
                return;
            }
            sessionStorage.setItem(SESSION_KEY, pw);
            document.getElementById('lock').style.display = 'none';
            document.getElementById('app').style.display = 'flex';
            document.getElementById('prompt').focus();
        }

        document.getElementById('pw').addEventListener('keydown', e => { if (e.key === 'Enter') unlock(); });
        if (pw) verifyAndShow();

        function newChat() {
            sessionId = null;
            document.getElementById('chat').innerHTML = '';
            document.getElementById('status').textContent = '';
            document.getElementById('prompt').focus();
        }

        function appendMessage(role, text) {
            const chat = document.getElementById('chat');
            if (chat.children.length > 0) {
                const hr = document.createElement('hr');
                hr.className = 'divider';
                chat.appendChild(hr);
            }
            const div = document.createElement('div');
            div.className = 'msg';
            const label = document.createElement('div');
            label.className = 'msg-label ' + (role === 'you' ? 'you' : '');
            label.textContent = role === 'you' ? 'You' : 'Claude';
            const body = document.createElement('div');
            body.className = 'msg-body ' + role;
            if (text) body.textContent = text;
            div.appendChild(label);
            div.appendChild(body);
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
            return body;
        }

        async function run() {
            const promptEl = document.getElementById('prompt');
            const prompt = promptEl.value.trim();
            if (!prompt) return;
            const btn = document.getElementById('runBtn');
            const statusEl = document.getElementById('status');

            btn.disabled = true;
            promptEl.value = '';

            appendMessage('you', prompt);
            const claudeBody = appendMessage('claude', '');

            // Elapsed timer
            const runStart = Date.now();
            statusEl.textContent = 'Running 0s';
            const timerInterval = setInterval(() => {
                const s = Math.floor((Date.now() - runStart) / 1000);
                const m = Math.floor(s / 60), sec = s % 60;
                statusEl.textContent = 'Running ' + (m > 0 ? m + 'm ' : '') + sec + 's';
            }, 1000);

            function appendText(text) {
                const last = claudeBody.lastChild;
                if (last && last.nodeType === Node.TEXT_NODE) {
                    last.textContent += text;
                } else {
                    claudeBody.appendChild(document.createTextNode(text));
                }
                document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
            }

            function appendTool(desc) {
                const el = document.createElement('span');
                el.className = 'tool-call';
                el.textContent = '\u2699 ' + desc;
                claudeBody.appendChild(el);
                document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
            }

            function done() {
                clearInterval(timerInterval);
                const s = Math.floor((Date.now() - runStart) / 1000);
                const m = Math.floor(s / 60), sec = s % 60;
                statusEl.textContent = 'Done in ' + (m > 0 ? m + 'm ' : '') + sec + 's';
                setTimeout(() => { statusEl.textContent = ''; }, 4000);
                btn.disabled = false;
                document.getElementById('prompt').focus();
            }

            try {
                const res = await fetch('/api/claude/run', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'X-Claude-Password': pw},
                    body: JSON.stringify({prompt, session_id: sessionId})
                });

                if (res.status === 401) { sessionStorage.removeItem(SESSION_KEY); location.reload(); return; }

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const {done: streamDone, value} = await reader.read();
                    if (streamDone) break;
                    buffer += decoder.decode(value, {stream: true});
                    const lines = buffer.split('\\n');
                    buffer = lines.pop();
                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const data = line.slice(6);
                        if (data === '[DONE]') { done(); return; }
                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.type === 'session') {
                                sessionId = parsed.session_id;
                            } else if (parsed.type === 'text') {
                                appendText(parsed.text);
                            } else if (parsed.type === 'tool') {
                                appendTool(parsed.desc);
                            }
                        } catch {}
                    }
                }
            } catch (err) {
                appendText('[Error: ' + err.message + ']');
            }
            done();
        }

        document.addEventListener('keydown', e => {
            if (e.ctrlKey && e.key === 'Enter' && document.getElementById('app').style.display !== 'none') run();
        });

        // ---- Running ----
        let runRefreshTimer = null;
        function openRunning() {
            document.getElementById('runModal').style.display = 'block';
            loadRunning();
            runRefreshTimer = setInterval(loadRunning, 3000);
        }
        function closeRunning() {
            document.getElementById('runModal').style.display = 'none';
            clearInterval(runRefreshTimer);
        }
        document.getElementById('runModal').addEventListener('click', e => {
            if (e.target === document.getElementById('runModal')) closeRunning();
        });

        async function loadRunning() {
            const list = document.getElementById('runList');
            try {
                const res = await fetch('/api/claude/running', { headers: {'X-Claude-Password': pw} });
                const runs = await res.json();
                if (!runs.length) {
                    list.innerHTML = '<div style="padding:20px;color:#4b5563;font-size:12px;">No active runs.</div>';
                    return;
                }
                list.innerHTML = runs.map(r => {
                    const elapsed = Math.floor((Date.now() - new Date(r.started_at)) / 1000);
                    const mins = Math.floor(elapsed / 60), secs = elapsed % 60;
                    const elapsedStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                    return `<div class="run-entry"><div class="run-time"><span class="run-dot"></span>Running for ${elapsedStr} &nbsp;&middot;&nbsp; PID ${r.pid}</div><div class="run-prompt">${escHtml(r.prompt)}</div><div class="run-pid">session: ${r.session_id}</div><button class="run-kill" onclick="killRun('${r.entry_id}',${r.pid})">Kill process</button></div>`;
                }).join('');
            } catch {
                list.innerHTML = '<div style="padding:20px;color:#f87171;font-size:12px;">Failed to load.</div>';
            }
        }

        async function killRun(entryId, pid) {
            if (!confirm('Kill this process (PID ' + pid + ')?')) return;
            await fetch('/api/claude/running/' + entryId, {
                method: 'DELETE',
                headers: {'X-Claude-Password': pw}
            });
            loadRunning();
        }

        // ---- History ----
        function openHistory() {
            document.getElementById('histModal').style.display = 'block';
            document.getElementById('histDetail').style.display = 'none';
            loadHistoryList();
        }
        function closeHistory() {
            document.getElementById('histModal').style.display = 'none';
        }
        document.getElementById('histModal').addEventListener('click', e => {
            if (e.target === document.getElementById('histModal')) closeHistory();
        });

        async function loadHistoryList() {
            const list = document.getElementById('histList');
            list.innerHTML = '<div style="padding:20px;color:#4b5563;font-size:12px;">Loading...</div>';
            try {
                const res = await fetch('/api/claude/history', { headers: {'X-Claude-Password': pw} });
                const entries = await res.json();
                if (!entries.length) {
                    list.innerHTML = '<div style="padding:20px;color:#4b5563;font-size:12px;">No history yet.</div>';
                    return;
                }
                list.innerHTML = entries.map(e => {
                    const hasResp = e.has_response;
                    const cls = hasResp ? 'hist-entry' : 'hist-entry no-response';
                    const preview = escHtml(hasResp ? e.preview : '(no response - click to copy prompt)');
                    return `<div class="${cls}" onclick="showHistDetail('${e.id}')"><div class="hist-time">${new Date(e.timestamp).toLocaleString()}</div><div class="hist-prompt">${escHtml(e.prompt)}</div><div class="hist-preview">${preview}</div></div>`;
                }).join('');
            } catch {
                list.innerHTML = '<div style="padding:20px;color:#f87171;font-size:12px;">Failed to load history.</div>';
            }
        }

        function showHistList() {
            document.getElementById('histDetail').style.display = 'none';
        }

        async function showHistDetail(id) {
            const detail = document.getElementById('histDetail');
            detail.style.display = 'flex';
            const body = document.getElementById('histDetailBody');
            body.textContent = 'Loading...';
            body.className = '';
            try {
                const res = await fetch('/api/claude/history/' + id, { headers: {'X-Claude-Password': pw} });
                const entry = await res.json();
                _currentDetailPrompt = entry.prompt;
                document.getElementById('histDetailPrompt').textContent = entry.prompt;
                if (entry.response) {
                    body.textContent = entry.response;
                    body.className = '';
                } else {
                    body.textContent = '(no response was captured for this run)';
                    body.className = 'no-response';
                }
            } catch {
                body.textContent = 'Failed to load.';
            }
        }

        function copyPrompt() {
            if (!_currentDetailPrompt) return;
            navigator.clipboard.writeText(_currentDetailPrompt).then(() => {
                const btn = document.getElementById('histCopyPrompt');
                btn.textContent = 'Copied!';
                setTimeout(() => { btn.textContent = 'Copy prompt'; }, 2000);
            });
        }

        function escHtml(s) {
            return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }
    </script>
</body>
</html>"""


class PromptRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None


def _check_password(x_claude_password: str):
    if x_claude_password != _PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _save_history(entry_id: str, session_id: str, prompt: str, response: str):
    ts = datetime.now(timezone.utc).isoformat()
    path = _HISTORY_DIR / f"{entry_id}.json"
    # Preserve original timestamp if file already exists
    if path.exists():
        try:
            existing = json.loads(path.read_text())
            ts = existing.get("timestamp", ts)
        except Exception:
            pass
    data = {
        "id": entry_id,
        "session_id": session_id,
        "timestamp": ts,
        "prompt": prompt,
        "response": response,
        "preview": response[:200].replace("\n", " ") if response else "",
    }
    path.write_text(json.dumps(data, ensure_ascii=False))


@router.get("/api/claude", response_class=HTMLResponse)
async def claude_ui():
    from fastapi.responses import HTMLResponse as _HR
    return _HR(_HTML, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.post("/api/claude/auth")
async def claude_auth(x_claude_password: str = Header(default="")):
    _check_password(x_claude_password)
    return JSONResponse({"ok": True})


@router.get("/api/claude/history")
async def get_history(x_claude_password: str = Header(default="")):
    _check_password(x_claude_password)
    entries = []
    for f in sorted(_HISTORY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            entries.append({
                "id": data["id"],
                "timestamp": data["timestamp"],
                "prompt": data["prompt"],
                "preview": data.get("preview", ""),
                "has_response": bool(data.get("response", "")),
            })
        except Exception:
            pass
    return JSONResponse(entries)


@router.get("/api/claude/running")
async def get_running(x_claude_password: str = Header(default="")):
    _check_password(x_claude_password)
    return JSONResponse(list(_active_runs.values()))


@router.delete("/api/claude/running/{entry_id}")
async def kill_run(entry_id: str, x_claude_password: str = Header(default="")):
    _check_password(x_claude_password)
    run = _active_runs.get(entry_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        import signal, os
        os.killpg(os.getpgid(run["pid"]), signal.SIGTERM)
    except Exception:
        pass
    _active_runs.pop(entry_id, None)
    return JSONResponse({"ok": True})


@router.get("/api/claude/history/{entry_id}")
async def get_history_entry(entry_id: str, x_claude_password: str = Header(default="")):
    _check_password(x_claude_password)
    path = _HISTORY_DIR / f"{entry_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return JSONResponse(json.loads(path.read_text()))


async def _stream_claude(prompt: str, session_id: Optional[str]):
    if session_id:
        args = [_CLAUDE_BIN, "--print", "--output-format", "stream-json", "--verbose",
                "--dangerously-skip-permissions", "--resume", session_id, prompt]
        new_session_id = session_id
    else:
        new_session_id = str(uuid.uuid4())
        args = [_CLAUDE_BIN, "--print", "--output-format", "stream-json", "--verbose",
                "--dangerously-skip-permissions", "--session-id", new_session_id, prompt]

    entry_id = str(uuid.uuid4())
    yield f"data: {json.dumps({'type': 'session', 'session_id': new_session_id})}\n\n"

    # Save prompt immediately — always captured even if run crashes
    _save_history(entry_id, new_session_id, prompt, "")

    chunks = []
    # partial tool input accumulator: index -> {name, partial_json}
    _tool_acc: dict = {}

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    _active_runs[entry_id] = {
        "entry_id": entry_id,
        "session_id": new_session_id,
        "prompt": prompt,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "pid": proc.pid,
    }
    try:
        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=10.0)
                if not line:
                    break
                raw = line.decode("utf-8", errors="replace").rstrip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    etype = obj.get("type", "")

                    # Higher-level Claude CLI format
                    if etype == "assistant":
                        for block in obj.get("message", {}).get("content", []):
                            if block.get("type") == "text":
                                t = block["text"]
                                if t:
                                    chunks.append(t)
                                    yield f"data: {json.dumps({'type': 'text', 'text': t})}\n\n"
                            elif block.get("type") == "tool_use":
                                desc = _format_tool_desc(block.get("name", "?"), block.get("input", {}))
                                yield f"data: {json.dumps({'type': 'tool', 'desc': desc})}\n\n"

                    elif etype == "result":
                        t = obj.get("result", "")
                        if t and not chunks:
                            chunks.append(t)
                            yield f"data: {json.dumps({'type': 'text', 'text': t})}\n\n"

                    # Low-level streaming API events (--verbose may emit these)
                    elif etype == "content_block_start":
                        block = obj.get("content_block", {})
                        idx = obj.get("index", 0)
                        if block.get("type") == "tool_use":
                            _tool_acc[idx] = {"name": block.get("name", "?"), "partial": ""}

                    elif etype == "content_block_delta":
                        idx = obj.get("index", 0)
                        delta = obj.get("delta", {})
                        if delta.get("type") == "text_delta":
                            t = delta.get("text", "")
                            if t:
                                chunks.append(t)
                                yield f"data: {json.dumps({'type': 'text', 'text': t})}\n\n"
                        elif delta.get("type") == "input_json_delta" and idx in _tool_acc:
                            _tool_acc[idx]["partial"] += delta.get("partial_json", "")

                    elif etype == "content_block_stop":
                        idx = obj.get("index", 0)
                        if idx in _tool_acc:
                            info = _tool_acc.pop(idx)
                            try:
                                inp = json.loads(info["partial"]) if info["partial"] else {}
                            except Exception:
                                inp = {}
                            desc = _format_tool_desc(info["name"], inp)
                            yield f"data: {json.dumps({'type': 'tool', 'desc': desc})}\n\n"

                    # Ignore: system, user, message_start, message_delta, message_stop, ping

                except json.JSONDecodeError:
                    # Not JSON — plain text output
                    chunks.append(raw + "\n")
                    yield f"data: {json.dumps({'type': 'text', 'text': raw + chr(10)})}\n\n"

            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        await proc.wait()
    finally:
        _active_runs.pop(entry_id, None)
        response = "".join(chunks)
        if not response:
            rc = proc.returncode if proc.returncode is not None else "?"
            response = f"(Process exited with code {rc} — no output was captured)"
        _save_history(entry_id, new_session_id, prompt, response)

    yield "data: [DONE]\n\n"


@router.post("/api/claude/run")
async def run_claude(req: PromptRequest, x_claude_password: str = Header(default="")):
    _check_password(x_claude_password)
    return StreamingResponse(
        _stream_claude(req.prompt, req.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
