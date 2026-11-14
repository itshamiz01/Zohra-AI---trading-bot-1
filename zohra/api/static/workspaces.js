/* Shared workspace rendering keeps backend strings out of HTML. */
const workspaceLoaders = {
    research: () => loadWorkspace('research-events-list', '/api/v1/research'),
    memory: loadMemory,
    learning: () => loadWorkspace('learning-records', '/api/v1/learning'),
    automation: () => loadWorkspace('automation-workflows-grid', '/api/v1/automation/workflows'),
    voice: () => loadWorkspace('voice-diagnostics-grid', '/api/v1/voice/diagnostics'),
    vision: () => loadWorkspace('vision-diagnostics-grid', '/api/v1/vision/diagnostics'),
    plugin: loadPlugins,
    capabilities: loadCapabilities,
    evolution: loadEvolution,
    settings: loadSettings
};

let capabilityRecords = [];
let capabilityControlBusy = false;
const nativeWindowsState = {};
const documentDraft = {format:'pdf',filename:'report.pdf',title:'',content:''};
let documentArtifacts = [];
const pdfInspection = {filename:'',page:1,query:'',result:null,error:'',busy:false};
const codeInspection = {path:'zohra/services/tool_execution/catalog.py',symbol:'',result:null,error:'',busy:false};

async function loadCapabilities() {
    const list = document.getElementById('capability-list');
    try {
        const data = await apiData('/api/v1/assistant/capabilities');
        capabilityRecords = data.tools || [];
        documentArtifacts = (await apiData(`/api/v1/assistant/documents?session_id=${encodeURIComponent(conversationSessionId())}`)).documents || [];
        document.getElementById('capability-security').textContent = `${data.security.scope}. ${data.security.strong_authentication}.`;
        renderCapabilities(); renderCapabilityApproval();
        await loadCapabilityActivity();
    } catch (error) { list.textContent = `Unavailable: ${error.message}`; }
}

function renderCapabilities() {
    const list = document.getElementById('capability-list');
    const query = document.getElementById('capability-query').value.toLowerCase();
    const state = document.getElementById('capability-state').value;
    list.replaceChildren();
    capabilityRecords.filter(tool => (!state || tool.availability === state) &&
        `${tool.name} ${tool.description} ${tool.category}`.toLowerCase().includes(query)).forEach(tool => {
        const row = element('div', undefined, 'capability-row');
        const heading = element('div', undefined, 'capability-heading');
        heading.append(element('strong', tool.name), element('span', tool.availability, 'capability-badge'));
        if (tool.controllable) {
            const label = element('label', 'Enabled');
            const checkbox = element('input'); checkbox.type = 'checkbox'; checkbox.checked = tool.enabled;
            checkbox.setAttribute('aria-label', `Enable ${tool.name}`);
            checkbox.disabled = capabilityControlBusy || confirmationBusy || Boolean(assistantTextController);
            checkbox.onchange = () => requestCapabilityControl(tool, checkbox.checked);
            label.prepend(checkbox); heading.append(label);
        }
        row.append(heading, element('p', tool.description));
        if (tool.reason !== tool.description) row.append(element('p', tool.reason, 'capability-muted'));
        const details = element('details'); details.append(element('summary', 'Permissions and contract'));
        const text = element('pre'); text.textContent = JSON.stringify({platform:tool.platform, permissions:tool.permissions,
            risk_level:tool.risk_level, confirmation_required:tool.confirmation_required, reversible:tool.reversible,
            private_output:tool.private_output,
            timeout_sec:tool.timeout_sec, dependencies:tool.dependencies, input_schema:tool.input_schema,
            output_schema:tool.output_schema, error_codes:tool.error_codes, last_execution:tool.last_execution}, null, 2);
        details.append(text); row.append(details); list.append(row);
        if (['windows.audio','windows.display'].includes(tool.name) && ['Available','Execution Failed'].includes(tool.availability)) renderWindowsControl(row, tool);
        if (tool.name === 'documents.create') renderDocumentControl(row, tool);
        if (tool.name === 'coding.explain') renderCodeInspection(row, tool);
    });
    if (!list.childElementCount) list.append(element('p', 'No matching capabilities.'));
}

function documentDownloadLink(artifact) {
    if (!/^[a-f0-9-]{36}$/.test(artifact.artifact_id || '')) return null;
    const link = element('a', undefined, 'document-download');
    link.href = `/api/v1/assistant/documents/${artifact.artifact_id}?session_id=${encodeURIComponent(conversationSessionId())}`;
    link.download = artifact.filename;
    const icon = element('span',undefined,'document-icon document-icon-download'); icon.setAttribute('aria-hidden','true');
    link.append(icon, document.createTextNode(` ${artifact.filename}`));
    link.setAttribute('aria-label', `Download ${artifact.filename}`);
    return link;
}

function renderDocumentControl(row, tool) {
    const form = element('form',undefined,'document-controls');
    const disabled = tool.availability !== 'Available' || !tool.enabled || capabilityControlBusy || confirmationBusy ||
        voiceRequestPending || Boolean(assistantTextController) || Boolean(pendingAssistantAction);
    const field = (name, control) => {
        const label = element('label',name); label.append(control); form.append(label); return control;
    };
    const format = element('select'); format.setAttribute('aria-label','Document format');
    [['pdf','PDF'],['docx','Word'],['xlsx','Excel']].forEach(([value,text]) => {const option = element('option',text); option.value = value; format.append(option);});
    format.value = documentDraft.format; format.disabled = disabled; field('Format',format);
    format.onchange = () => {
        const previous = documentDraft.format; documentDraft.format = format.value;
        documentDraft.filename = documentDraft.filename.replace(new RegExp(`\\.${previous}$`,'i'),`.` + format.value);
        renderCapabilities();
    };
    for (const [key,name,maximum] of [['filename','Filename',120],['title','Title',180]]) {
        const input = element('input'); input.type = 'text'; input.value = documentDraft[key]; input.maxLength = maximum;
        input.disabled = disabled; input.required = key === 'filename'; input.setAttribute('aria-label',`Document ${key}`);
        input.oninput = () => {documentDraft[key] = input.value;};
        field(name,input); if (key === 'title') input.parentElement.className = 'document-title';
    }
    const content = element('textarea'); content.rows = 7; content.value = documentDraft.content; content.maxLength = 100000;
    content.required = true; content.disabled = disabled; content.setAttribute('aria-label','Document content');
    content.oninput = () => {documentDraft.content = content.value;};
    const label = field(documentDraft.format === 'xlsx' ? 'CSV or JSON rows' : 'Content',content); label.parentElement.className = 'document-content';
    const preview = element('button',undefined,'view-agents-btn'); preview.type = 'submit'; preview.disabled = disabled;
    const icon = element('span',undefined,'document-icon document-icon-file'); icon.setAttribute('aria-hidden','true');
    preview.append(icon,document.createTextNode(' Preview creation'));
    form.append(preview);
    form.onsubmit = async event => {
        event.preventDefault();
        if (disabled || capabilityControlBusy || confirmationBusy || voiceRequestPending || assistantTextController || pendingAssistantAction) return;
        capabilityControlBusy = true; renderCapabilities();
        try {
            const result = await apiData('/api/v1/assistant/documents',{method:'POST',signal:AbortSignal.timeout(45000),headers:{'Content-Type':'application/json'},
                body:JSON.stringify({session_id:conversationSessionId(),args:{...documentDraft}})});
            addConversationMessage('user',`Create ${documentDraft.format.toUpperCase()} document ${documentDraft.filename}`);
            showAssistantResult(result);
        } catch (error) {document.getElementById('capability-control-result').textContent = error.message;}
        finally {capabilityControlBusy = false; renderCapabilities(); renderCapabilityApproval(); await loadCapabilityActivity();}
    };
    row.append(form);
    const files = element('div',undefined,'document-files');
    const pdfTool = capabilityRecords.find(record => record.name === 'document.pdf');
    const canInspect = pdfTool?.availability === 'Available' && pdfTool.enabled;
    if (!canInspect) pdfInspection.result = null;
    documentArtifacts.slice(0,10).forEach(artifact => {
        const link = documentDownloadLink(artifact);
        if (link) {
            const item = element('div'); item.append(link,element('small',`${artifact.bytes} bytes | ${artifact.created || 'Verified'}`));
            if (artifact.format === 'pdf') {
                const inspect = element('button',undefined,'document-inspect-button'); inspect.type = 'button';
                inspect.disabled = !canInspect || pdfInspection.busy;
                inspect.title = canInspect ? `Read or search ${artifact.filename}` : 'PDF inspection is unavailable';
                inspect.setAttribute('aria-label',`Read or search ${artifact.filename}`);
                const icon = element('span',undefined,'document-icon document-icon-file'); icon.setAttribute('aria-hidden','true');
                inspect.append(icon,document.createTextNode(' Read'));
                inspect.onclick = () => inspectSavedPdf(artifact.filename,'',1);
                item.append(inspect);
            }
            files.append(item);
        }
    });
    row.append(files);
    if (pdfInspection.filename && documentArtifacts.some(item => item.filename === pdfInspection.filename && item.format === 'pdf')) {
        const panel = element('section',undefined,'pdf-inspection');
        panel.setAttribute('aria-label',`PDF contents: ${pdfInspection.filename}`);
        panel.append(element('h4',pdfInspection.filename));
        const search = element('form',undefined,'pdf-search');
        const queryLabel = element('label','Find in PDF');
        const query = element('input'); query.type = 'search'; query.maxLength = 120; query.value = pdfInspection.query;
        query.disabled = !canInspect || pdfInspection.busy; query.setAttribute('aria-label','Find text in PDF');
        query.oninput = () => {pdfInspection.query = query.value;}; queryLabel.append(query);
        const submit = element('button','Search'); submit.type = 'submit'; submit.disabled = !canInspect || pdfInspection.busy;
        search.append(queryLabel,submit);
        search.onsubmit = event => {event.preventDefault(); if (query.value.trim()) inspectSavedPdf(pdfInspection.filename,query.value.trim());};
        panel.append(search);
        if (pdfInspection.busy) panel.append(element('p','Reading PDF...'));
        if (pdfInspection.error) panel.append(element('p',pdfInspection.error,'pdf-error'));
        const data = pdfInspection.result;
        if (data) {
            panel.append(element('p',`${data.page_count} pages | ${data.source}`,'pdf-meta'));
            if (data.query) {
                panel.append(element('p',`${data.match_count} matches${data.matches_truncated ? ' (first 10 shown)' : ''}`));
                data.matches.forEach(match => {
                    const line = element('div',undefined,'pdf-match');
                    const pageButton = element('button',`Page ${match.page}`); pageButton.type = 'button';
                    pageButton.disabled = pdfInspection.busy;
                    pageButton.onclick = () => inspectSavedPdf(pdfInspection.filename,'',match.page);
                    line.append(pageButton,element('span',match.snippet)); panel.append(line);
                });
            } else {
                data.pages.forEach(page => {
                    panel.append(element('h5',`Page ${page.page}`),element('pre',page.text || 'No selectable text on this page.','pdf-page-text'));
                    if (page.truncated) panel.append(element('p','Page preview limited to 4,000 characters.','pdf-meta'));
                });
                if (data.page_count > 1) {
                    const navigation = element('div',undefined,'pdf-navigation');
                    for (const [label,target] of [['Previous',pdfInspection.page-1],['Next',pdfInspection.page+1]]) {
                        const button = element('button',label); button.type = 'button'; button.disabled = target < 1 || target > data.page_count || pdfInspection.busy;
                        button.onclick = () => inspectSavedPdf(pdfInspection.filename,'',target);
                        navigation.append(button);
                    }
                    panel.append(navigation);
                }
            }
        }
        row.append(panel);
    }
}

async function inspectSavedPdf(filename, query='', page=null) {
    if (pdfInspection.busy) return;
    pdfInspection.filename = filename; pdfInspection.page = page || 1; pdfInspection.query = query;
    pdfInspection.result = null; pdfInspection.error = ''; pdfInspection.busy = true; renderCapabilities();
    const params = new URLSearchParams({session_id:conversationSessionId(),filename});
    if (query) params.set('query',query);
    else if (page) params.set('page',String(page));
    try {
        const result = await apiData(`/api/v1/assistant/pdf/inspect?${params}`,{signal:AbortSignal.timeout(25000)});
        if (result.status !== 'success') throw new Error(result.error?.message || result.response || 'PDF inspection failed');
        pdfInspection.result = result.data;
    } catch (error) {pdfInspection.error = error.message; }
    finally {pdfInspection.busy = false; renderCapabilities(); await loadCapabilityActivity();}
}

function renderCodeInspection(row, tool) {
    const disabled = tool.availability !== 'Available' || !tool.enabled || codeInspection.busy || capabilityControlBusy ||
        confirmationBusy || voiceRequestPending || Boolean(assistantTextController);
    if (tool.availability !== 'Available' || !tool.enabled) codeInspection.result = null;
    const form = element('form',undefined,'document-controls code-inspection-form');
    for (const [key,labelText,maximum,required] of [['path','Project Python file',240,true],['symbol','Function or class (optional)',160,false]]) {
        const label = element('label',labelText);
        const input = element('input'); input.type = 'text'; input.maxLength = maximum; input.value = codeInspection[key];
        input.required = required; input.disabled = disabled; input.setAttribute('aria-label',labelText);
        input.oninput = () => {codeInspection[key] = input.value;};
        label.append(input); form.append(label);
    }
    const inspect = element('button','Inspect source','view-agents-btn'); inspect.type = 'submit'; inspect.disabled = disabled;
    form.append(inspect);
    form.onsubmit = event => {
        event.preventDefault();
        if (!disabled && codeInspection.path.trim()) inspectProjectCode();
    };
    row.append(form);
    const panel = element('section',undefined,'code-inspection'); panel.setAttribute('aria-live','polite');
    if (codeInspection.busy) panel.append(element('p','Reading source...'));
    if (codeInspection.error) panel.append(element('p',codeInspection.error,'pdf-error'));
    const data = codeInspection.result;
    if (data) {
        panel.append(element('h4',`${data.kind}: ${data.symbol || data.path}`),element('p',data.summary));
        panel.append(element('p',`${data.source} | ${data.path}:${data.line_start}-${data.line_end} | Read-only`,'pdf-meta'));
        if (data.references?.length) {
            const references = element('ul');
            data.references.slice(0,40).forEach(ref => references.append(element('li',`${ref.kind} ${ref.name} | ${ref.reference}-${ref.line_end}`)));
            panel.append(references);
        }
        if (data.calls?.length) panel.append(element('p',`Calls mentioned: ${data.calls.join(', ')}`));
    }
    row.append(panel);
}

async function inspectProjectCode() {
    if (codeInspection.busy) return;
    codeInspection.result = null; codeInspection.error = ''; codeInspection.busy = true; renderCapabilities();
    const params = new URLSearchParams({session_id:conversationSessionId(),path:codeInspection.path,symbol:codeInspection.symbol});
    try {
        const result = await apiData(`/api/v1/assistant/code/inspect?${params}`,{signal:AbortSignal.timeout(20000)});
        if (result.status !== 'success') throw new Error(result.error?.message || result.response || 'Source inspection failed');
        codeInspection.result = result.data;
    } catch (error) {codeInspection.error = error.message;}
    finally {codeInspection.busy = false; renderCapabilities(); await loadCapabilityActivity();}
}

function renderWindowsControl(row, tool) {
    const kind = tool.name === 'windows.audio' ? 'audio' : 'display';
    const panel = element('div', undefined, 'native-controls');
    const refresh = element('button', 'Read current settings', 'view-agents-btn'); refresh.type = 'button';
    refresh.disabled = capabilityControlBusy || confirmationBusy;
    refresh.onclick = async () => {
        refresh.disabled = true;
        try {
            const result = await apiData(`/api/v1/assistant/windows/status?kind=${kind}&session_id=${encodeURIComponent(conversationSessionId())}`);
            nativeWindowsState[kind] = result.status === 'success' ? result.data : {error:result.response};
        } catch (error) { nativeWindowsState[kind] = {error:error.message}; }
        renderCapabilities(); await loadCapabilityActivity();
    };
    panel.append(refresh);
    const data = nativeWindowsState[kind];
    if (data?.error) panel.append(element('p', data.error));
    else if (data) {
        const pending = tool.availability !== 'Available' || capabilityControlBusy || confirmationBusy || voiceRequestPending || Boolean(assistantTextController) || Boolean(pendingAssistantAction);
        const slider = (name, value, commit) => {
            const label = element('label', name);
            const input = element('input'); input.type = 'range'; input.min = '0'; input.max = '100'; input.step = '1'; input.value = String(Math.round(value));
            input.setAttribute('aria-label', name); input.disabled = pending || !tool.enabled;
            const output = element('output', `${input.value}%`);
            input.oninput = () => {output.textContent = `${input.value}%`;};
            input.onchange = () => commit(Number(input.value));
            label.append(input,output); panel.append(label);
        };
        if (kind === 'audio') {
            panel.append(element('p', `${data.device_name}: ${data.volume}%`));
            slider('Master volume', data.volume, volume => requestWindowsControl('configure_audio',{volume}));
            const label = element('label', 'Mute', 'native-toggle'); const mute = element('input'); mute.type = 'checkbox'; mute.checked = data.muted;
            mute.setAttribute('aria-label','Mute master audio'); mute.disabled = pending || !tool.enabled;
            mute.onchange = () => {const muted = mute.checked; mute.checked = data.muted; requestWindowsControl('configure_audio',{muted});};
            label.prepend(mute); panel.append(label);
        } else {
            data.monitors.forEach(monitor => slider(`Brightness ${monitor.monitor_id}`, monitor.brightness,
                brightness => requestWindowsControl('configure_brightness',{brightness,monitor_id:monitor.monitor_id})));
        }
        panel.append(element('time', data.observed_at));
    }
    row.append(panel);
}

async function requestWindowsControl(action, args) {
    if (capabilityControlBusy || confirmationBusy || voiceRequestPending || assistantTextController || pendingAssistantAction) return;
    capabilityControlBusy = true; renderCapabilities();
    try {
        const result = await apiData('/api/v1/assistant/windows/control',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({session_id:conversationSessionId(),action,args})});
        addConversationMessage('user', `Request Windows control: ${JSON.stringify(args)}`);
        showAssistantResult(result);
    } catch (error) { document.getElementById('capability-control-result').textContent = error.message; }
    finally {capabilityControlBusy = false; renderCapabilities(); renderCapabilityApproval(); await loadCapabilityActivity();}
}

async function requestCapabilityControl(tool, enabled) {
    if (capabilityControlBusy || confirmationBusy || voiceRequestPending || assistantTextController) return;
    capabilityControlBusy = true; renderCapabilities();
    try {
        const result = await apiData('/api/v1/assistant/capabilities/control', {method:'POST',
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:conversationSessionId(), tool_id:tool.name, enabled})});
        addConversationMessage('user', `${enabled ? 'Enable' : 'Disable'} tool ${tool.name}`);
        showAssistantResult(result);
        document.getElementById('capability-control-result').textContent = result.response;
    } catch (error) { document.getElementById('capability-control-result').textContent = error.message; }
    finally { capabilityControlBusy = false; renderCapabilities(); renderCapabilityApproval(); }
}

function renderCapabilityApproval() {
    const panel = document.getElementById('capability-approval');
    if (!panel) return;
    panel.replaceChildren(); panel.hidden = !pendingAssistantAction;
    if (!pendingAssistantAction) return;
    panel.append(element('p', pendingAssistantAction.description), element('p', pendingAssistantAction.consequence));
    [true, false].forEach(decision => {
        const button = element('button', decision ? 'Confirm' : 'Cancel'); button.type = 'button';
        button.disabled = confirmationBusy || voiceRequestPending;
        button.onclick = () => confirmAssistantAction(pendingAssistantAction.id, decision);
        panel.append(button);
    });
}

async function loadCapabilityActivity() {
    const data = await apiData(`/api/v1/assistant/activity?session_id=${encodeURIComponent(conversationSessionId())}`);
    const container = document.getElementById('capability-activity'); container.replaceChildren();
    (data.events || []).forEach(event => {
        const row = element('div', undefined, 'capability-activity-row');
        row.append(element('strong', event.tool_id), element('span', event.status), element('span', `${event.elapsed_ms} ms`),
            element('span', event.verified ? 'Verified' : 'Not verified'), element('time', `${event.created} UTC`));
        if (event.error) row.append(element('p', event.error.message || JSON.stringify(event.error)));
        container.append(row);
    });
    if (!container.childElementCount) container.append(element('p', 'No assistant executions recorded in this session.'));
}

async function apiData(url, options = {}) {
    const response = await fetch(url, {signal: AbortSignal.timeout(15000), ...options});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`);
    return data;
}

function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
}

function displayValue(value) {
    if (value == null) return 'Unavailable';
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    return String(value);
}

function renderRecords(container, data) {
    container.replaceChildren();
    if (Array.isArray(data)) {
        if (!data.length) container.append(element('p', 'No records yet.', 'workspace-empty'));
        data.forEach(record => {
            const row = element('div', undefined, 'workspace-record');
            if (record && typeof record === 'object') renderRecords(row, record);
            else row.textContent = displayValue(record);
            container.append(row);
        });
    } else if (data && typeof data === 'object') {
        Object.entries(data).forEach(([key, value]) => {
            const group = element('div', undefined, 'workspace-field');
            group.append(element('strong', key.replaceAll('_', ' ')));
            if (value && typeof value === 'object') {
                const details = element('details');
                details.open = ['records', 'workflows', 'plugins', 'diagnostics', 'projects', 'sources', 'collections', 'consensus', 'components'].includes(key);
                details.append(element('summary', Array.isArray(value) ? `${value.length} records` : 'Details'));
                const content = element('div');
                renderRecords(content, value);
                details.append(content);
                group.append(details);
            } else group.append(element('span', displayValue(value)));
            container.append(group);
        });
    } else container.textContent = displayValue(data);
}

async function loadWorkspace(id, url) {
    const node = document.getElementById(id);
    node.textContent = 'Loading...';
    try { renderRecords(node, await apiData(url)); }
    catch (error) { node.textContent = `Unavailable: ${error.message}`; }
}

function loadMemory() {
    const q = document.getElementById('memory-query').value.trim();
    return loadWorkspace('memory-results', `/api/v1/memory?q=${encodeURIComponent(q)}`);
}

async function loadSettings() {
    const status = document.getElementById('settings-result');
    status.textContent = 'Loading...';
    try {
        const data = await apiData('/api/v1/settings');
        document.getElementById('risk-setting').value = data.risk_per_trade_pct * 100;
        document.getElementById('positions-setting').value = data.max_open_positions;
        status.textContent = 'Current runtime settings';
    } catch (error) { status.textContent = error.message; }
}

async function saveSettings(event) {
    event.preventDefault();
    const status = document.getElementById('settings-result');
    const button = event.submitter;
    button.disabled = true;
    try {
        await apiData('/api/v1/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
            risk_per_trade_pct: Number(document.getElementById('risk-setting').value) / 100,
            max_open_positions: Number(document.getElementById('positions-setting').value)
        })});
        status.textContent = 'Applied to this running session.';
    } catch (error) { status.textContent = `Could not save: ${error.message}`; }
    finally { button.disabled = false; }
}

async function loadPlugins() {
    const node = document.getElementById('plugins-grid');
    node.textContent = 'Loading...';
    try {
        const data = await apiData('/api/v1/plugins');
        node.replaceChildren();
        if (!data.plugins.length) node.textContent = 'No installed plugins.';
        data.plugins.forEach(plugin => {
            const row = element('div', undefined, 'workspace-record');
            renderRecords(row, plugin);
            const button = element('button', plugin.status === 'ENABLED' ? 'Disable' : 'Enable', 'view-agents-btn');
            button.onclick = async () => {
                button.disabled = true;
                try {
                    await apiData(`/api/v1/plugins/${plugin.status === 'ENABLED' ? 'disable' : 'enable'}`, {
                        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({plugin_id: plugin.id})
                    });
                    await loadPlugins();
                } catch (error) { button.disabled = false; row.append(element('p', error.message)); }
            };
            row.append(button);
            node.append(row);
        });
    } catch (error) { node.textContent = `Unavailable: ${error.message}`; }
}

async function loadEvolution() {
    await Promise.all([
        loadWorkspace('evolution-health-grid', '/api/v1/evolution/health'),
        loadWorkspace('evolution-recommendations-list', '/api/v1/evolution/recommendations')
    ]);
}

async function runVisionCapture() {
    const node = document.getElementById('vision-capture-panel');
    node.textContent = 'Capturing...';
    try {
        const {image, ...data} = await apiData('/api/v1/vision/capture');
        renderRecords(node, data);
        if (image?.startsWith('data:image/png;base64,')) {
            const preview = element('img');
            preview.src = image;
            preview.alt = 'Captured screen';
            preview.style.maxWidth = '100%';
            node.prepend(preview);
        }
    } catch (error) { node.textContent = `Capture failed: ${error.message}`; }
}

function money(value) { return value == null ? 'Unavailable' : `$${Number(value).toFixed(2)}`; }
function pct(value) { return value == null ? 'Unavailable' : `${Number(value).toFixed(1)}%`; }
function setText(id, value) { const node = document.getElementById(id); if (node) node.textContent = value; }

async function fetchTelemetryData() {
    const account = currentAccount;
    try {
        const data = await apiData(`/api/v1/os/telemetry?account=${encodeURIComponent(account)}`);
        if (account !== currentAccount) return;
        const td = data.trading_division;
        const selector = document.getElementById('os-account-selector');
        const options = [{account_id: 'all', name: `ALL FLEET (${td.accounts.length} Accounts)`}, ...td.accounts];
        const signature = JSON.stringify(options.map(a => [a.account_id, a.name, a.masked_login]));
        if (selector.dataset.options !== signature) {
            selector.replaceChildren(...options.map(a => {
                const option = element('option', `${a.name}${a.masked_login ? ` (${a.masked_login})` : ''}`);
                option.value = a.account_id; return option;
            }));
            selector.dataset.options = signature;
            selector.value = currentAccount;
        }
        setText('execution-mode', data.execution_mode.toUpperCase());
        setText('td-balance', money(td.balance));
        setText('td-equity', money(td.equity));
        setText('td-pnl', money(td.daily_pnl));
        setText('td-positions', displayValue(td.open_positions));
        updateRingGauge('cpu-ring-circle', 'cpu-pct-txt', data.system_performance.cpu_usage_pct);
        updateRingGauge('ram-ring-circle', 'ram-pct-txt', data.system_performance.ram_usage_pct);
        setText('gpu-pct-txt', data.system_performance.gpu_usage);
        for (const kind of ['core', 'active', 'busy', 'offline']) setText(`agent-stat-${kind}`, data.ai_agents[`${kind}_count`]);
        setText('health-ring-txt', 'API');
        document.querySelector('.status-state-live').textContent = data.system_status;
        const ops = document.querySelector('.ops-list');
        ops.replaceChildren();
        if (!data.active_operations.length) ops.append(element('p', 'No registered operations.'));
        data.active_operations.forEach(op => ops.append(element('div', `${op.name}: ${op.status}`, 'op-item')));
    } catch (error) {
        if (account !== currentAccount) return;
        document.querySelector('.status-state-live').textContent = 'DISCONNECTED';
        ['td-balance', 'td-equity', 'td-pnl', 'td-positions'].forEach(id => setText(id, 'Unavailable'));
    }
}

function fillTable(id, rows, columns, emptyMessage) {
    const body = document.getElementById(id);
    body.replaceChildren();
    if (!rows.length) {
        const row = element('tr');
        const cell = element('td', emptyMessage);
        cell.colSpan = columns.length;
        row.append(cell); body.append(row); return;
    }
    rows.forEach(record => {
        const row = element('tr');
        columns.forEach(get => {
            const cell = element('td');
            const value = get(record);
            if (value instanceof Node) cell.append(value);
            else cell.textContent = displayValue(value);
            row.append(cell);
        });
        body.append(row);
    });
}

async function loadTradingData() {
    const account = currentAccount;
    for (const [path, id, open] of [['open', 'trading-positions-tbody', true], ['history', 'trading-history-tbody', false]]) {
        try {
            const data = await apiData(`/api/v1/trades/${path}?limit=25&account=${encodeURIComponent(account)}`);
            if (account !== currentAccount) return;
            const ticket = t => t.mt5_ticket || t.ticket || t.trade_id;
            const columns = open ? [ticket, t => t.account_id, t => t.symbol, t => t.direction,
                t => t.position_size_lots ?? t.volume, t => t.entry_price, t => t.current_price,
                t => t.stop_loss, t => t.take_profit, t => money(t.profit_loss), t => {
                    const button = element('button', 'Close', 'view-agents-btn');
                    button.disabled = !t.can_close;
                    button.title = t.can_close ? 'Close this position' : 'Connected account required';
                    button.onclick = () => closeSingleTrade(ticket(t)); return button;
                }] : [t => t.timestamp_close, ticket, t => t.symbol, t => t.direction,
                t => t.entry_price, t => t.exit_price, t => money(t.profit_loss), t => t.strategy, t => t.reason_for_exit];
            fillTable(id, data.trades, columns, 'No recorded trades for this account.');
        } catch (error) {
            if (account !== currentAccount) return;
            fillTable(id, [], Array(open ? 11 : 9), `Unavailable: ${error.message}`);
        }
    }
}

async function closeSingleTrade(ticket) {
    if (!confirm(`Close position ${ticket}?`)) return;
    try {
        await apiData(`/api/v1/commands/close/${encodeURIComponent(ticket)}`, {method: 'POST'});
        await Promise.all([loadTradingData(), fetchTelemetryData()]);
    } catch (error) { alert(error.message); }
}

async function closeAllPositions() {
    if (!confirm('Close all positions on the API-connected account? Other fleet accounts are not affected.')) return;
    try {
        const data = await apiData('/api/v1/commands/close-all', {method: 'POST'});
        alert(`Closed ${data.positions_closed} positions on the connected account.`);
        await Promise.all([loadTradingData(), fetchTelemetryData()]);
    } catch (error) { alert(error.message); }
}

async function exportJournalCSV() {
    try {
        const data = await apiData(`/api/v1/trades/history?limit=500&account=${encodeURIComponent(currentAccount)}`);
        const columns = ['trade_id', 'mt5_ticket', 'symbol', 'direction', 'entry_price', 'exit_price', 'profit_loss', 'timestamp_close', 'strategy'];
        const escape = v => '"' + String(v ?? '').replace(/^[=+@-]/, "'$&").replaceAll('"', '""') + '"';
        const csv = [columns.join(','), ...data.trades.map(t => columns.map(c => escape(t[c])).join(','))].join('\r\n');
        const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
        const link = element('a'); link.href = url; link.download = 'zohra-trades.csv'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { alert(error.message); }
}

function loadAgentsList() { return loadWorkspace('agents-cards-grid', '/api/v1/agents'); }
function loadDashboardConsensus() { return loadWorkspace('dash-consensus-grid', '/api/v1/consensus'); }

async function runWorkflow(event) {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    try {
        const data = await apiData('/api/v1/automation/trigger', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command: document.getElementById('workflow-command').value})});
        setText('workflow-result', `Started: ${data.name}`);
        await workspaceLoaders.automation();
    } catch (error) { setText('workflow-result', error.message); }
    finally { button.disabled = false; }
}

let voiceSocket = null;
let voiceProcessor = null;
let voiceSource = null;
let voiceSpeaking = false;
let lastSpeech = 0;
let voiceReply = '';
let voicePlayback = null;
const voiceQueue = [];
let voiceSessionId = '';
let queuedVoiceText = null;
let voiceRequestPending = false;
let currentAssistantMessage = null;
const conversationMessages = [];
let assistantTextController = null;
let pendingAssistantAction = null;
let confirmationBusy = false;
function conversationSessionId() {
    if (!voiceSessionId) {
        try { voiceSessionId = sessionStorage.getItem('zohra-conversation-id') || ''; } catch {}
        voiceSessionId ||= crypto.randomUUID();
        try { sessionStorage.setItem('zohra-conversation-id', voiceSessionId); } catch {}
    }
    return voiceSessionId;
}
function updateVoiceCaptureUI() {
    ['holo-talk-toggle', 'voice-talk-toggle'].forEach(id => {
        const toggle = document.getElementById(id);
        if (toggle) toggle.checked = isListening;
    });
    document.getElementById('voice-talk-button')?.setAttribute('aria-pressed', String(isListening));
}
function updateConversationControls() {
    const speaking = Boolean(voicePlayback || voiceQueue.length);
    document.querySelectorAll?.('[data-conversation-stop]').forEach(button => {
        button.disabled = confirmationBusy || (!voiceRequestPending && !assistantTextController && !speaking);
    });
    document.querySelectorAll?.('.conversation-form button[type="submit"]').forEach(button => {
        button.disabled = Boolean(assistantTextController || confirmationBusy);
    });
}
function stopConversationReply() {
    if (confirmationBusy) return;
    assistantTextController?.abort(); assistantTextController = null;
    cancelVoiceResponse(); clearVoicePlayback();
    voiceRequestPending = false; queuedVoiceText = null;
    updateConversationControls();
    const status = isListening ? 'Listening' : 'Microphone off';
    setText('voice-status-txt', status); setHoloControlStatus(status);
}
function conversationSourceUrl(value) {
    try {
        if (typeof value !== 'string' || /[\s\\\x00-\x1f]/.test(value)) return null;
        const url = new URL(value);
        const host = url.hostname.toLowerCase();
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
            (url.port && !['80', '443'].includes(url.port)) || !host.includes('.') ||
            /(?:^0\.|^127\.|^10\.|^192\.168\.|^169\.254\.|^172\.(?:1[6-9]|2\d|3[01])\.|\.(?:localhost|local|internal|test)$)/.test(host)) return null;
        return url.href;
    } catch { return null; }
}
function renderConversation() {
    renderCapabilityApproval();
    ['voice-conversation', 'command-conversation'].forEach(id => {
        const log = document.getElementById(id);
        if (!log?.replaceChildren) return;
        log.replaceChildren();
        conversationMessages.slice(-12).forEach(message => {
            const row = document.createElement('p');
            const label = document.createElement('strong');
            label.textContent = message.role === 'user' ? 'You: ' : 'Zohra: ';
            row.append(label, document.createTextNode(message.content));
            log.append(row);
            const sources = (message.sources || []).slice(0, 10).filter(source => conversationSourceUrl(source.url));
            if (sources.length) {
                const tray = document.createElement('details');
                tray.className = 'conversation-sources';
                const summary = document.createElement('summary');
                summary.textContent = `Sources (${sources.length})`;
                const evidence = document.createElement('small');
                evidence.textContent = 'Search excerpts';
                const list = document.createElement('ul');
                sources.forEach(source => {
                    const item = document.createElement('li');
                    const link = document.createElement('a');
                    link.href = conversationSourceUrl(source.url); link.target = '_blank';
                    link.rel = 'noopener noreferrer'; link.textContent = source.title;
                    const detail = document.createElement('small');
                    const published = source.published_at ? new Date(source.published_at) : null;
                    const retrieved = source.retrieved_at ? new Date(source.retrieved_at) : null;
                    detail.textContent = [source.publisher,
                        published && !Number.isNaN(published.getTime()) ? `Reported date ${published.toLocaleDateString()}` : '',
                        retrieved && !Number.isNaN(retrieved.getTime()) ? `Searched ${retrieved.toLocaleString()}` : ''].filter(Boolean).join(' | ');
                    item.append(link, detail); list.append(item);
                });
                tray.append(summary, evidence, list); log.append(tray);
            }
            if (message.data) {
                if (message.data.verified === true && message.data.artifact_id) {
                    const download = documentDownloadLink(message.data);
                    if (download) log.append(download);
                }
                const details = document.createElement('details');
                const summary = document.createElement('summary'); summary.textContent = 'Backend data';
                const content = document.createElement('pre'); content.textContent = JSON.stringify(message.data, null, 2);
                details.append(summary, content); log.append(details);
            }
        });
        if (pendingAssistantAction) {
            const pending = document.createElement('div'); pending.className = 'conversation-confirmation';
            const description = document.createElement('p'); description.textContent = pendingAssistantAction.description;
            const consequence = document.createElement('p'); consequence.textContent = pendingAssistantAction.consequence;
            pending.append(description, consequence);
            [true, false].forEach(decision => {
                const button = document.createElement('button'); button.type = 'button';
                button.textContent = decision ? 'Confirm' : 'Cancel'; button.disabled = confirmationBusy || voiceRequestPending;
                button.addEventListener('click', () => confirmAssistantAction(pendingAssistantAction.id, decision));
                pending.append(button);
            });
            log.append(pending);
        }
        log.scrollTop = log.scrollHeight;
    });
}
function addConversationMessage(role, content) {
    const message = {role, content};
    conversationMessages.push(message);
    if (conversationMessages.length > 40) conversationMessages.shift();
    renderConversation();
    return message;
}
async function sendAssistantText(event, inputId) {
    event.preventDefault();
    const input = document.getElementById(inputId);
    const text = input.value.trim();
    if (!text || text.length > 4000 || assistantTextController || confirmationBusy) return;
    clearVoicePlayback();
    cancelVoiceResponse();
    input.value = '';
    if (handleHoloVoiceCommand(text)) return;
    setHoloFormation(true);
    addConversationMessage('user', text);
    pendingAssistantAction = null;
    const controller = new AbortController(); assistantTextController = controller;
    updateConversationControls(); setText('voice-status-txt', 'Processing');
    try {
        const result = await apiData('/api/v1/assistant/message', {method:'POST', signal:controller.signal,
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:conversationSessionId(), message:text})});
        if (assistantTextController !== controller) return;
        showAssistantResult(result);
    } catch (error) {
        if (error.name !== 'AbortError') addConversationMessage('assistant', error.message);
    } finally {
        if (assistantTextController === controller) assistantTextController = null;
        updateConversationControls();
    }
}
function showAssistantResult(result) {
    rememberNativeResult(result);
    if (result.status === 'success' && result.data?.verified === true && result.data.artifact_id &&
        !documentArtifacts.some(artifact => artifact.artifact_id === result.data.artifact_id)) documentArtifacts.unshift(result.data);
    const message = addConversationMessage('assistant', result.response || result.error?.message || 'No response returned.');
    message.sources = result.sources || []; message.data = result.data;
    pendingAssistantAction = result.pending || null;
    renderConversation();
    if (currentView === 'capabilities') document.getElementById('capability-control-result').textContent = result.response || result.error?.message || '';
    setText('voice-status-txt', result.status === 'pending_confirmation' ? 'Awaiting confirmation' : 'Microphone off');
}
function rememberNativeResult(result) {
    if (result.status === 'success' && result.data?.after) {
        if (result.tool_id === 'windows.audio' && nativeWindowsState.audio) nativeWindowsState.audio = {...nativeWindowsState.audio,...result.data.after,observed_at:result.data.observed_at};
        if (result.tool_id === 'windows.display' && nativeWindowsState.display) {
            nativeWindowsState.display.monitors = nativeWindowsState.display.monitors.map(monitor => monitor.monitor_id === result.data.after.monitor_id ? result.data.after : monitor);
            nativeWindowsState.display.observed_at = result.data.observed_at;
        }
    }
}
async function confirmAssistantAction(id, decision) {
    if (confirmationBusy || assistantTextController || voiceRequestPending || pendingAssistantAction?.id !== id) return;
    confirmationBusy = true; renderConversation(); updateConversationControls();
    try {
        const result = await apiData('/api/v1/assistant/confirm', {method:'POST',
            signal:AbortSignal.timeout(45000),
            headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:conversationSessionId(), confirmation_id:id, decision})});
        addConversationMessage('user', decision ? 'Confirm' : 'Cancel');
        showAssistantResult(result);
    } catch (error) {
        pendingAssistantAction = null;
        await loadAssistantHistory();
        addConversationMessage('assistant', `Confirmation response unavailable: ${error.message}. Execution status may be unknown.`);
    } finally {
        confirmationBusy = false; renderConversation(); updateConversationControls();
        if (currentView === 'capabilities') await loadCapabilities();
    }
}
async function loadAssistantHistory() {
    try {
        const result = await apiData(`/api/v1/assistant/history?session_id=${encodeURIComponent(conversationSessionId())}`);
        if (assistantTextController) return;
        conversationMessages.splice(0, conversationMessages.length, ...(result.messages || []));
        pendingAssistantAction = result.pending || null; renderConversation();
    } catch (error) { setText('voice-status-txt', error.message); }
}
function flushVoiceText() {
    if (queuedVoiceText && voiceSocket?.readyState === WebSocket.OPEN) {
        voiceSocket.send(JSON.stringify({type:'text_input', content:queuedVoiceText}));
        queuedVoiceText = null;
    }
}
function cancelVoiceResponse() {
    if (voiceSocket?.readyState === WebSocket.OPEN) {
        voiceSocket.send(JSON.stringify({type:'portrait_hidden'}));
    }
}
function clearVoicePlayback() {
    if (voicePlayback) {
        voicePlayback.onended = null; voicePlayback.onerror = null;
        disconnectHologramPlayback(voicePlayback);
        voicePlayback.pause(); URL.revokeObjectURL(voicePlayback.src); voicePlayback = null;
    }
    voiceQueue.splice(0).forEach(url => URL.revokeObjectURL(url));
    updateConversationControls();
}
async function playVoiceQueue() {
    if (voicePlayback || !voiceQueue.length) return;
    const url = voiceQueue.shift();
    const playback = new Audio(url);
    voicePlayback = playback;
    updateConversationControls();
    setText('voice-status-txt', 'Speaking');
    const finished = () => {
        URL.revokeObjectURL(url);
        disconnectHologramPlayback(playback);
        if (voicePlayback !== playback) return;
        voicePlayback = null; playVoiceQueue(); updateConversationControls();
        if (!voicePlayback && !voiceQueue.length) {
            const status = voiceRequestPending ? 'Thinking' : isListening ? 'Listening' : 'Microphone off';
            setText('voice-status-txt', status);
            setHoloControlStatus(status === 'Microphone off' ? 'Zohra ready' : status);
        }
    };
    playback.onended = finished;
    playback.onerror = finished;
    try {
        await connectHologramPlayback(playback, () => voicePlayback === playback);
    } catch (error) {
        console.warn('Voice visualization unavailable:', error.message);
    }
    if (voicePlayback !== playback) return;
    playback.play().catch(() => { setText('voice-status-txt', 'Audio playback unavailable'); finished(); });
}
function startVoiceSession() {
    if (voiceSocket && voiceSocket.readyState <= WebSocket.OPEN) { attachVoiceCapture(); return; }
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/voice/stream?session_id=${conversationSessionId()}`);
    voiceSocket = socket;
    voiceSocket.onopen = () => {
        socket.send(JSON.stringify({type:'history'}));
        flushVoiceText();
    };
    voiceSocket.onmessage = event => {
        if (voiceSocket !== socket) return;
        if (event.data instanceof Blob) {
            voiceQueue.push(URL.createObjectURL(event.data));
            playVoiceQueue();
            return;
        }
        if (typeof event.data !== 'string') return;
        let data;
        try { data = JSON.parse(event.data); } catch { return; }
        if (data.type === 'interrupt') clearVoicePlayback();
        if (data.type === 'transcript') {
            pendingAssistantAction = null;
            voiceReply = ''; currentAssistantMessage = null; setText('voice-transcript', data.content);
            if (!handleHoloVoiceCommand(data.content)) addConversationMessage('user', data.content);
        }
        if (data.type === 'history') {
            conversationMessages.splice(0, conversationMessages.length, ...(data.messages || []));
            renderConversation();
        }
        if (data.type === 'portrait' && data.action === 'hide') setHoloFormation(false);
        if (data.type === 'token') {
            voiceReply += data.content; setText('voice-transcript', voiceReply);
            currentAssistantMessage ||= addConversationMessage('assistant', '');
            currentAssistantMessage.content = voiceReply; renderConversation();
        }
        if (data.type === 'sources') {
            currentAssistantMessage ||= addConversationMessage('assistant', '');
            currentAssistantMessage.sources = data.sources || []; renderConversation();
        }
        if (data.type === 'assistant_result') {
            rememberNativeResult(data.result);
            pendingAssistantAction = data.result.pending || null;
            currentAssistantMessage ||= addConversationMessage('assistant', '');
            currentAssistantMessage.data = data.result.data || null;
            renderConversation(); renderCapabilityApproval();
            if (currentView === 'capabilities') loadCapabilities().catch(() => {});
        }
        if (data.type === 'acknowledgement') {
            addConversationMessage('assistant', data.content);
        }
        if (data.type === 'tool') {
            const status = {search_web:'Searching the web', get_backend_update:'Reading backend update', manage_tasks:'Updating tasks'}[data.name] || 'Thinking';
            setText('voice-status-txt', status); setHoloControlStatus(status);
        }
        if (data.type === 'error') {
            setText('voice-transcript', data.content);
            setHoloControlStatus(data.content);
            voiceRequestPending = false;
        }
        if (data.type === 'response_done') voiceRequestPending = false;
        if (data.type === 'status') {
            if (data.content === 'LISTENING') voiceRequestPending = false;
            const status = data.content === 'LISTENING' ? (voicePlayback || voiceQueue.length ? 'Speaking' : isListening ? 'Listening' : holoSoundEnabled ? 'Sound controls listening' : 'Microphone off') : data.content.replaceAll('_', ' ');
            setText('voice-status-txt', status);
            setHoloControlStatus(status === 'Microphone off' ? 'Zohra ready' : status);
        }
        updateConversationControls();
    };
    voiceSocket.onerror = () => setText('voice-status-txt', 'Voice connection unavailable');
    voiceSocket.onclose = () => {
        if (voiceSocket !== socket) return;
        stopVoiceSession();
        isListening = false;
        holoSoundEnabled = false;
        document.getElementById('holo-sound-toggle').checked = false;
        releaseHoloMicIfUnused();
        setHoloControlStatus('Sound connection closed');
        setText('voice-status-txt', 'Microphone off');
        updateVoiceCaptureUI();
    };
    attachVoiceCapture();
}
function attachVoiceCapture() {
    if (voiceProcessor || !micStream || !holoAudioCtx) return;
    voiceSource = holoAudioCtx.createMediaStreamSource(micStream);
    voiceProcessor = holoAudioCtx.createScriptProcessor(4096, 1, 1);
    voiceProcessor.onaudioprocess = event => {
        if ((!isListening && !holoSoundEnabled) || voiceSocket?.readyState !== WebSocket.OPEN) return;
        // Do not transcribe the assistant's own loudspeaker output as a new request.
        if ((voicePlayback && !voicePlayback.paused) ||
                (typeof holoIgnoreMicUntil !== 'undefined' && performance.now() < holoIgnoreMicUntil)) return;
        const input = event.inputBuffer.getChannelData(0);
        if (holoSoundEnabled) {
            const soundEvent = sampleHoloSound(input);
            if (soundEvent || holoSoundState.whistleMs > 0) return;
        }
        const rms = Math.sqrt(input.reduce((s, x) => s + x*x, 0) / input.length);
        if (rms > 0.015) {
            lastSpeech = performance.now();
            if (!voiceSpeaking) {
                clearVoicePlayback(); voiceRequestPending = true;
                voiceSocket.send(JSON.stringify({type:'speech_started'})); voiceSpeaking = true;
            }
        }
        if (!voiceSpeaking) return;
        const ratio = holoAudioCtx.sampleRate / 16000;
        const pcm = new Int16Array(Math.floor(input.length / ratio));
        for (let i = 0; i < pcm.length; i++) pcm[i] = Math.max(-1, Math.min(1, input[Math.floor(i * ratio)])) * 32767;
        voiceSocket.send(pcm.buffer);
        if (performance.now() - lastSpeech > 800) {
            voiceSocket.send(JSON.stringify({type:'speech_stopped', control_only:!isListening})); voiceSpeaking = false;
        }
    };
    voiceSource.connect(voiceProcessor);
    voiceProcessor.connect(holoAudioCtx.destination);
}
function stopVoiceSession() {
    clearVoicePlayback();
    if (voiceSocket) voiceSocket.onclose = null;
    voiceProcessor?.disconnect(); voiceSource?.disconnect(); voiceSocket?.close();
    voiceProcessor = null; voiceSource = null; voiceSocket = null; voiceSpeaking = false;
    voiceRequestPending = false; queuedVoiceText = null;
    updateConversationControls();
}

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nav-item, .summary-card').forEach(node => {
        node.tabIndex = 0;
        node.setAttribute('role', 'button');
        node.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); node.click(); }
        });
    });
    setText('voice-status-txt', 'Microphone off');
    loadAssistantHistory();
    setInterval(() => {
        if (document.hidden) return;
        if (currentView === 'trading') loadTradingData();
        if (currentView === 'dashboard') loadDashboardConsensus();
        if (currentView === 'automation') workspaceLoaders.automation();
        if (currentView === 'capabilities' && !capabilityControlBusy && !confirmationBusy) {
            // Preserve focus and in-progress typing while refreshing execution history.
            if (pendingAssistantAction || document.activeElement?.closest('.document-controls, .pdf-inspection, .code-inspection')) loadCapabilityActivity().catch(() => {});
            else loadCapabilities();
        }
    }, 10000);
});
