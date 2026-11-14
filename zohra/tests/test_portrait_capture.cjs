const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function captureHarness(options = {}) {
    const code = fs.readFileSync(path.join(__dirname, '../api/static/workspaces.js'), 'utf8');
    const sockets = [], messages = [], hides = [], stopped = [], statuses = [], requests = [];
    const processor = {connect() {}, disconnect() { stopped.push('processor'); }};
    const source = {connect() {}, disconnect() { stopped.push('source'); }};
    class Socket {
        static OPEN = 1;
        constructor(url) { this.url = url; this.readyState = 1; sockets.push(this); }
        send(text) { if (typeof text === 'string') messages.push(JSON.parse(text)); }
        close() { this.readyState = 3; this.onclose?.(); }
    }
    let now = 1000;
    const context = vm.createContext({WebSocket: Socket, Blob, location: {protocol:'http:', host:'localhost'},
        AbortController, AbortSignal, apiData: async (url, opts) => { requests.push({url, ...opts}); return options.reply || {response:'CHAT: Hello', status:'success'}; },
        crypto: {randomUUID: () => 'test'}, holoAudioCtx: {sampleRate:48000, destination:{},
            createMediaStreamSource: () => source, createScriptProcessor: () => processor},
        micStream: options.withoutMic ? null : {}, isListening: false, holoSoundEnabled: !options.withoutMic,
        holoSoundState: {whistleMs: 0}, sampleHoloSound: () => null,
        setText(id, value) { statuses.push([id, value]); }, setHoloControlStatus() {}, releaseHoloMicIfUnused() {},
        setHoloFormation: value => hides.push(value), handleHoloVoiceCommand: text => { hides.push(text); return false; },
        sessionStorage: {getItem: key => options.storage?.get(key) || null,
            setItem: (key, value) => options.storage?.set(key, value)},
        document: {getElementById: () => ({checked:true, value:'Hello Zohra', setAttribute() {}})},
        performance: {now: () => now}, disconnectHologramPlayback() {}, URL: class extends URL { static revokeObjectURL() {} },
        console, renderCapabilityApproval() {}, currentView:'command-center', nativeWindowsState:{}});
    vm.runInContext(code.slice(code.indexOf('let voiceSocket ='), code.indexOf("document.addEventListener('DOMContentLoaded'")), context);
    context.startVoiceSession();
    function frame(level, time) {
        now = time;
        processor.onaudioprocess({inputBuffer:{getChannelData: () => new Float32Array(4096).fill(level)}});
    }
    return {context, sockets, messages, hides, stopped, statuses, requests, frame};
}

test('Sound alone captures dismissal phrases in control-only mode, without duplicate streams', () => {
    const h = captureHarness();
    h.context.startVoiceSession();
    assert.equal(h.sockets.length, 1);
    h.frame(0.04, 1000);
    h.frame(0, 1850);
    assert.ok(h.messages.some(message => message.type === 'speech_stopped' && message.control_only === true));
    h.context.isListening = true;
    h.frame(0.04, 2000);
    h.frame(0, 2850);
    assert.ok(h.messages.some(message => message.type === 'speech_stopped' && message.control_only === false));
});

test('server transcript and portrait events reach the actual visibility control', () => {
    const h = captureHarness();
    h.sockets[0].onmessage({data: JSON.stringify({type:'transcript', content:'over'})});
    h.sockets[0].onmessage({data: JSON.stringify({type:'portrait', action:'hide'})});
    assert.deepEqual(h.hides, ['over', false]);
});

test('voice confirmations and verified native data reach the same conversation UI', () => {
    const h = captureHarness({withoutMic:true});
    const socket = h.sockets[0];
    const receive = message => socket.onmessage({data:JSON.stringify(message)});
    receive({type:'transcript',content:'set volume to 25%'});
    receive({type:'assistant_result',result:{status:'pending_confirmation',pending:{id:'voice-pending',description:'Set master volume to 25%',consequence:'Changes audio'}}});
    assert.equal(vm.runInContext('pendingAssistantAction.id',h.context),'voice-pending');
    assert.equal(h.requests.length,0);
    receive({type:'token',content:'TASK: Confirm this exact action.'});
    receive({type:'transcript',content:'confirm'});
    assert.equal(vm.runInContext('pendingAssistantAction',h.context),null);
    h.context.nativeWindowsState.audio = {volume:50,muted:false};
    receive({type:'assistant_result',result:{status:'success',tool_id:'windows.audio',data:{after:{volume:25,muted:false},verified:true,observed_at:'now'}}});
    receive({type:'token',content:'TASK: Completed.'});
    assert.equal(h.context.nativeWindowsState.audio.volume,25);
    assert.equal(vm.runInContext('currentAssistantMessage.data.verified',h.context),true);
    assert.equal(vm.runInContext('pendingAssistantAction',h.context),null);
});

test('stopping capture disables socket callbacks and disconnects all processing', () => {
    const h = captureHarness();
    h.context.stopVoiceSession();
    assert.equal(h.sockets[0].onclose, null);
    assert.equal(h.sockets[0].readyState, 3);
    assert.deepEqual(h.stopped, ['processor', 'source']);
});

test('hiding the face cancels the backend reply rather than letting later audio restart it', () => {
    const h = captureHarness();
    h.context.cancelVoiceResponse();
    assert.deepEqual(h.messages, [{type:'portrait_hidden'}]);
});

test('conversation identity survives reconnects and a dashboard reload', () => {
    const storage = new Map();
    const h = captureHarness({storage});
    const first = h.sockets[0].url;
    h.context.stopVoiceSession();
    h.context.startVoiceSession();
    assert.equal(h.sockets[1].url, first);
    assert.equal(captureHarness({storage}).sockets[0].url, first);
});

test('typed conversation uses the confirmed HTTP bridge without microphone permission', async () => {
    const h = captureHarness({withoutMic:true});
    await h.context.sendAssistantText({preventDefault() {}}, 'assistant-message');
    assert.equal(h.requests[0].url, '/api/v1/assistant/message');
    assert.equal(JSON.parse(h.requests[0].body).message, 'Hello Zohra');
    assert.ok(!h.messages.some(message => message.type === 'text_input'));
    assert.deepEqual(h.hides, ['Hello Zohra', true]);
    assert.equal(h.context.isListening, false);
});

test('typed messages do not depend on socket readiness', async () => {
    const h = captureHarness({withoutMic:true});
    h.sockets[0].readyState = 0;
    await h.context.sendAssistantText({preventDefault() {}}, 'assistant-message');
    assert.equal(h.messages.length, 0);
    h.sockets[0].readyState = 1;
    h.sockets[0].onopen();
    assert.equal(h.requests.length, 1);
    assert.ok(!h.messages.some(message => message.type === 'text_input'));
    assert.ok(h.messages.some(message => message.type === 'history'));
});

test('two completed typed requests both use the same confirmation bridge', async () => {
    const h = captureHarness({withoutMic:true});
    await h.context.sendAssistantText({preventDefault() {}}, 'assistant-message');
    await h.context.sendAssistantText({preventDefault() {}}, 'assistant-message');
    assert.equal(h.requests.length, 2);
});

test('a pending write does not confirm itself; explicit buttons use a separate endpoint', async () => {
    const h = captureHarness({withoutMic:true, reply:{status:'pending_confirmation', response:'TASK: Confirm the file write.', pending:{id:'pending-1', description:'Create a file', consequence:'Writes a file'}}});
    await h.context.sendAssistantText({preventDefault() {}}, 'assistant-message');
    assert.equal(h.requests.length, 1);
    await h.context.confirmAssistantAction('pending-1', true);
    assert.equal(h.requests[1].url, '/api/v1/assistant/confirm');
    assert.equal(JSON.parse(h.requests[1].body).decision, true);
});

test('source links use public HTTP(S) and reject scripts, credentials, and local addresses', () => {
    const h = captureHarness({withoutMic:true});
    for (const value of ['javascript:alert(1)', 'file:///secret', 'http://localhost/',
        'http://127.0.0.1/', 'https://user:password@example.org/', 'https://example.org:8000/']) {
        assert.equal(h.context.conversationSourceUrl(value), null);
    }
    assert.equal(h.context.conversationSourceUrl('https://www.nasa.gov/'), 'https://www.nasa.gov/');
});

test('sources render safe text and survive a history reload, without entering spoken content', () => {
    const h = captureHarness({withoutMic:true});
    class Element {
        constructor(tag) { this.tag = tag; this.children = []; }
        append(...children) { this.children.push(...children); }
        replaceChildren(...children) { this.children = children; }
    }
    const log = new Element('log');
    h.context.document = {getElementById: id => id === 'command-conversation' ? log : null,
        createElement: tag => new Element(tag), createTextNode: text => ({text})};
    const sources = [{title:'<script>unsafe text</script>', url:'https://www.nasa.gov/', publisher:'NASA'}];
    h.sockets[0].onmessage({data: JSON.stringify({type:'sources', sources})});
    h.sockets[0].onmessage({data: JSON.stringify({type:'token', content:'Mission update.'})});
    const tray = log.children.find(child => child.tag === 'details');
    const link = tray.children.find(child => child.tag === 'ul').children[0].children[0];
    assert.equal(link.tag, 'a');
    assert.equal(link.textContent, '<script>unsafe text</script>');
    assert.equal(link.rel, 'noopener noreferrer');
    assert.equal(link.href, 'https://www.nasa.gov/');
    assert.equal(log.children[0].children[1].text, 'Mission update.');
    h.sockets[0].onmessage({data: JSON.stringify({type:'history', messages:[{role:'assistant', content:'Mission update.', sources}]})});
    assert.ok(log.children.some(child => child.tag === 'details'));
});

test('work acknowledgement appears before the separate result in conversation', () => {
    const h = captureHarness({withoutMic:true});
    h.sockets[0].onmessage({data: JSON.stringify({type:'transcript', content:'Search NASA'})});
    h.sockets[0].onmessage({data: JSON.stringify({type:'acknowledgement', content:'I will check public sources.'})});
    h.sockets[0].onmessage({data: JSON.stringify({type:'token', content:'NASA mission update.'})});
    const messages = vm.runInContext('JSON.stringify(conversationMessages)', h.context);
    assert.deepEqual(JSON.parse(messages).map(message => message.content),
        ['Search NASA', 'I will check public sources.', 'NASA mission update.']);
});

test('Speak status remains truthful while audio still plays after backend completion', () => {
    const h = captureHarness();
    h.context.isListening = true;
    vm.runInContext('voicePlayback = {paused:false};', h.context);
    h.sockets[0].onmessage({data: JSON.stringify({type:'status', content:'LISTENING'})});
    assert.deepEqual(h.statuses.at(-1), ['voice-status-txt', 'Speaking']);
});

test('Stop reply cancels the response but keeps Talk, the socket, and portrait intact', () => {
    const h = captureHarness();
    h.context.isListening = true;
    h.context.stopConversationReply();
    assert.equal(h.context.isListening, true);
    assert.equal(h.sockets[0].readyState, 1);
    assert.deepEqual(h.messages, [{type:'portrait_hidden'}]);
    assert.deepEqual(h.hides, []);
    assert.deepEqual(h.statuses.at(-1), ['voice-status-txt', 'Listening']);
});

test('outgoing speech is never recaptured as a user utterance', () => {
    const h = captureHarness();
    h.context.isListening = true;
    vm.runInContext('voicePlayback = {paused:false};', h.context);
    h.frame(0.3, 1000);
    assert.equal(h.messages.length, 0);
    vm.runInContext('voicePlayback = null;', h.context);
    h.frame(0.04, 2000);
    assert.ok(h.messages.some(message => message.type === 'speech_started'));
});

test('switching from typed conversation to Talk attaches capture once to the existing socket', () => {
    const h = captureHarness({withoutMic:true});
    h.context.micStream = {};
    h.context.isListening = true;
    h.context.startVoiceSession();
    h.context.startVoiceSession();
    assert.equal(h.sockets.length, 1);
    h.frame(0.04, 1000);
    h.frame(0, 1850);
    assert.ok(h.messages.some(message => message.type === 'speech_stopped' && message.control_only === false));
});

test('command center has only the face and bottom conversation, not division summary boxes', () => {
    const html = fs.readFileSync(path.join(__dirname, '../api/dashboard.html'), 'utf8');
    const center = html.slice(html.indexOf('id="view-command-center"'), html.indexOf('id="view-trading"'));
    assert.ok(center.includes('id="command-conversation"'));
    assert.ok(center.includes('id="command-message"'));
    assert.ok(!center.includes('class="summary-card"'));
    assert.ok(!html.includes('id="assistant-conversation"'));
    for (const name of ['trading', 'research', 'memory', 'learning', 'evolution']) {
        assert.ok(html.includes(`id="nav-${name}"`));
        assert.ok(html.includes(`id="view-${name}"`));
    }
});
