const writing = /\b(manuscript|chapter|character bible|continuity|line[ -]edit|developmental|novel|blurb|scene|pacing|plot|dialogue|publisher query|draft)\b/i;
const trading = /\b(trad(?:e|es|ing)|positions?|pnl|p&l|equity|drawdown|risk|bot|stop[ -]?loss|prop[ -]?firm|portfolio|account balance)\b/i;
const task = /\b(files?|folders?|directory|notepad|calculator|browser|search|research|summari[sz]e|remind|schedule|to[ -]do|tasks?|memory|cpu|ram|system|agents?|learning|volume|brightness|spotify|emails?|whatsapp|camera|screenshot|wifi|network|desktop|computer|phone|android|processes|shutdown|restart|pdf|excel|spreadsheet|workbook|website|wallpaper|playlist)\b/i;
const systemAction = /^(?:please\s+)?(?:open|close|launch|run|execute|create|write|save|delete|erase|clean|move|copy|rename|download|install|send|reply|forward|play|mute|unmute|shutdown|restart|sign out|sleep|hibernate|set|adjust|reduce|increase|decrease|turn (?:on|off)|khol(?:o)?|band karo|bhejo)\b|\u0916\u094b\u0932\u094b|\u092c\u0902\u0926 \u0915\u0930\u094b|\u092d\u0947\u091c\u094b|\u0921\u093f\u0932\u0940\u091f/i;

export function classify(text) {
  if (typeof text !== 'string' || !text.trim() || text.length > 4000) {
    return {lane: null, action: 'invalid', status: 'invalid', response: 'Enter a request of 1 to 4000 characters.'};
  }
  text = text.trim();
  const codeSymbol = text.match(/^(?:please\s+)?explain\s+(?:the\s+)?(?:function|class|method)\s+"([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?)"\s+in\s+"([^"]+)"\??$/i);
  if (codeSymbol) return {lane:'TASK',action:'code_inspect',args:{path:codeSymbol[2],symbol:codeSymbol[1]}};
  const codeFile = text.match(/^(?:please\s+)?(?:explain|inspect)\s+(?:the\s+)?(?:code|python\s+(?:code|file))\s+"([^"]+)"(?:\s+symbol\s+"([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?)")?\??$/i);
  if (codeFile) return {lane:'TASK',action:'code_inspect',args:{path:codeFile[1],symbol:codeFile[2] || ''}};
  const pdfRead = text.match(/^(?:please\s+)?(?:read|inspect|show)(?:\s+me)?\s+(?:the\s+)?pdf\s+"([^"]+)"(?:\s+page\s+(\d{1,3}))?\??$/i);
  if (pdfRead) return {lane:'TASK',action:'pdf_inspect',args:{filename:pdfRead[1],page:pdfRead[2] ? Number(pdfRead[2]) : null,query:''}};
  const pdfSearch = text.match(/^(?:please\s+)?search\s+(?:the\s+)?pdf\s+"([^"]+)"\s+for\s+(.+)$/i);
  if (pdfSearch) return {lane:'TASK',action:'pdf_inspect',args:{filename:pdfSearch[1],page:null,query:pdfSearch[2]}};
  const document = text.match(/^(?:please\s+)?(?:create|write|save|make|generate)\s+(?:a\s+)?(pdf|word(?:\s+document)?|docx|excel(?:\s+(?:spreadsheet|workbook))?|xlsx|spreadsheet)\s+(?:(?:named|called)\s+)?"([^"]+)"\s+(?:with|containing)\s+([\s\S]+)$/i) ||
    text.match(/^(pdf|word|docx|excel|xlsx)\s+"([^"]+)"\s+(?:banao|\u092c\u0928\u093e\u0913)\s+(?:with|mein|\u092e\u0947\u0902)\s+([\s\S]+)$/i);
  if (document) {
    const kind = document[1].toLowerCase();
    const format = kind.startsWith('word') || kind === 'docx' ? 'docx' : kind === 'pdf' ? 'pdf' : 'xlsx';
    return {lane:'TASK',action:'export_document',args:{format,filename:document[2],title:'',content:document[3]}};
  }
  if (/^(?:please\s+)?(?:create|write|save|make|generate)\s+(?:a\s+)?(?:pdf|word document|docx|excel|xlsx|spreadsheet)\b/i.test(text)) {
    return {lane:'TASK',action:'document_context',status:'needs_context',response:'TASK: Provide the document filename and exact content, or use the document form in Capability Center. No file has been created.'};
  }
  const volume = text.match(/^(?:please\s+)?(?:set|adjust|reduce|increase|decrease)(?:\s+(?:my|master|the))?\s+volume\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)?[.!]?$/i) ||
    text.match(/^volume\s+(\d{1,3})\s*(?:%|percent)?\s*(?:karo|kar do|\u0915\u0930\u094b|\u0915\u0930 \u0926\u094b)$/i) ||
    text.match(/^\u0906\u0935\u093e\u091c\s+(\d{1,3})\s*(?:%|\u092a\u094d\u0930\u0924\u093f\u0936\u0924)?\s*\u0915\u0930\u094b$/);
  if (volume) return {lane:'TASK',action:'configure_audio',args:{volume:Number(volume[1])}};
  const mute = text.match(/^(?:please\s+)?(mute|unmute)(?:\s+(?:my|the))?(?:\s+(?:computer|audio|speakers))?[.!]?$/i);
  if (mute) return {lane:'TASK',action:'configure_audio',args:{muted:mute[1].toLowerCase() === 'mute'}};
  const brightness = text.match(/^(?:please\s+)?(?:set|adjust|reduce|increase|decrease)(?:\s+(?:my|screen|the))?\s+brightness\s+(?:to\s+)?(\d{1,3})\s*(?:%|percent)?[.!]?$/i) ||
    text.match(/^brightness\s+(\d{1,3})\s*(?:%|percent)?\s*(?:karo|kar do|\u0915\u0930\u094b|\u0915\u0930 \u0926\u094b)$/i);
  if (brightness) return {lane:'TASK',action:'configure_brightness',args:{brightness:Number(brightness[1])}};
  if (/^(?:(?:show|check|what is)(?: my| the| current| master)? )?(?:volume|audio status|mute status)\??$/i.test(text)) return {lane:'TASK',action:'audio_status'};
  if (/^(?:(?:show|check|what is)(?: my| the| current| screen)? )?(?:brightness|display status|monitors)\??$/i.test(text)) return {lane:'TASK',action:'display_status'};
  const control = text.match(/^(enable|disable)\s+(?:tool|capability)\s+([a-z][a-z0-9_.]+)$/i);
  if (control) return {lane:'TASK', action:'set_tool_enabled', args:{tool_id:control[2].toLowerCase(), enabled:control[1].toLowerCase() === 'enable'}};
  if (/^(?:what can you do\??|(?:show|list)(?: me)?(?: your| available)? (?:tools|capabilities)|capabilities|tools)$/i.test(text) || /^(?:kya kar sakti ho|tools dikhao)$/i.test(text)) return {lane:'TASK',action:'capability_inventory'};
  if (/^(?:show|list|check|analy[sz]e|tell me)(?: my| the)? (?:running processes|processes|applications consuming.*ram|computer(?:'s)? performance|computer performance)$/i.test(text) || /^(?:processes|ram ka usage|computer slow kyun hai|\u0915\u0902\u092a\u094d\u092f\u0942\u091f\u0930 \u0938\u094d\u0932\u094b \u0915\u094d\u092f\u094b\u0902 \u0939\u0948)$/i.test(text)) return {lane:'TASK',action:'process_status'};
  if (/^(?:(?:show|check)(?: my| the)? )?(?:network status|network interfaces|local ip|internet status)$/i.test(text) || /^network dikhao$/i.test(text)) return {lane:'TASK',action:'network_status'};
  const file = text.match(/^(?:please\s+)?(?:write|create|save)\s+(?:a\s+)?file\s+"([^"]+)"\s+(?:with|containing)\s+([\s\S]+)$/i);
  if (file) return {lane: 'TASK', action: 'write_file', args: {path: file[1], content: file[2]}};
  const todo = text.match(/^(?:please\s+)?(?:add|create|save)\s+(?:a\s+)?(?:task|to[ -]do)\s*:?\s+([\s\S]+)$/i);
  if (todo) return {lane: 'TASK', action: 'create_task', args: {title: todo[1]}};
  const complete = text.match(/^(?:complete|finish)\s+task\s+#?(\d+)$/i);
  if (complete) return {lane: 'TASK', action: 'complete_task', args: {task_id: Number(complete[1])}};
  if (/^(?:list|show)(?: me)?\s+(?:my\s+)?(?:tasks|to[ -]dos)$/i.test(text)) return {lane: 'TASK', action: 'list_tasks'};
  const app = text.match(/^(?:please\s+)?(?:open|launch)\s+(notepad|calculator)$/i);
  if (app) return {lane: 'TASK', action: 'launch_app', args: {app: app[1].toLowerCase()}};
  const browser = text.match(/^(?:please\s+)?open\s+(?:browser\s+(?:to|at)\s+)?(https?:\/\/\S+)$/i);
  if (browser) return {lane:'TASK',action:'open_browser',args:{url:browser[1]}};
  const casual = /^(?:hi|hello|hey)(?:\s+zohra)?[.!]?\s*$|^(?:thanks|thank you)\b|\b(?:tell|sunao)\b.*\b(?:joke|jokes)\b/i.test(text);
  if (casual && !/\b(?:and|then)\b.*\b(?:close|open|write|pause|resume|change)\b/i.test(text)) return {lane: 'CHAT', action: 'chat'};
  const lanes = [trading.test(text) && 'TRADING', writing.test(text) && 'WRITING',
    (task.test(text) || (systemAction.test(text) && !trading.test(text) && !writing.test(text))) && 'TASK'].filter(Boolean);
  if (lanes.length > 1) return {lane: null, action: 'clarify', status: 'clarify', response: 'Which should I handle first: trading, writing, or the other task?'};
  const lane = lanes[0] || 'CHAT';
  if (lane === 'TRADING') {
    const mutation = /\b(?:close|buy|sell|pause|resume|halt|change|modify|set|increase|decrease|override|start|stop(?![ -]loss\b)|enable|disable|liquidate|execute|cancel|reset)\b/i.test(text) ||
      /(?:^|\b(?:please|can you|and|then)\s+)open\b/i.test(text);
    return {lane, action: mutation ? 'blocked_trading_write' : 'backend_update', domain: 'trading'};
  }
  if (lane === 'WRITING') {
    const modes = [/continuity|contradict/i.test(text) && 'CONTINUITY CHECK', /line[ -]edit/i.test(text) && 'LINE EDIT', /developmental feedback/i.test(text) && 'DEVELOPMENTAL FEEDBACK'].filter(Boolean);
    if (modes.length > 1) return {lane, action:'clarify', status:'clarify', response:'WRITING: Which mode should I use first: line edit, developmental feedback, or continuity check?'};
    return {lane, action:'writer', mode:modes[0] || (/sentence/i.test(text) ? 'LINE EDIT' : /draft|compose|write|blurb/i.test(text) ? 'DRAFT' : 'DEVELOPMENTAL FEEDBACK')};
  }
  if (lane === 'TASK') {
    if (/\b(?:search|research)\b/i.test(text)) return {lane, action: 'search', query: text};
    if (/\b(?:cpu|ram|system)\b/i.test(text)) return {lane, action: 'backend_update', domain: 'system'};
    if (/\b(?:memory|agents?|learning)\b/i.test(text)) return {lane, action: 'backend_update', domain: /memory/i.test(text) ? 'memory' : /learning/i.test(text) ? 'learning' : 'agents'};
    return {lane, action: 'unsupported', status: 'unsupported', response: 'TASK: That action is not connected. I can read backend updates, search public sources, inspect local Python code, manage confirmed to-dos, create local text/PDF/Word/Excel files after confirmation, read or search a verified PDF, or open a public browser page/Notepad/Calculator after confirmation.'};
  }
  return {lane, action: 'chat'};
}
