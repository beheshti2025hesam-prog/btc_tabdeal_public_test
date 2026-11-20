(() => {
'use strict';
const byId = id => document.getElementById(id);
const state = { payload: null, selected: null, query: '', category: '' };
const safetyExpected = { read_only: true, execution_enabled: false, orders_placed: false, policy_mutation: false };
const STATUS_COPY = {
 en: { loading: 'Loading documentation…', blocked: 'Documentation could not be verified. No content is displayed.' },
 fa: { loading: 'در حال بارگذاری مستندات…', blocked: 'اعتبار مستندات تأیید نشد؛ هیچ محتوایی نمایش داده نمی‌شود.' },
 de: { loading: 'Dokumentation wird geladen…', blocked: 'Die Dokumentation konnte nicht verifiziert werden. Es werden keine Inhalte angezeigt.' },
 fr: { loading: 'Chargement de la documentation…', blocked: 'La documentation n’a pas pu être vérifiée. Aucun contenu n’est affiché.' }
};
const language = () => ['fa','en','de','fr'].includes(window.HESDashboardLocale?.get?.()) ? window.HESDashboardLocale.get() : 'en';
const node = (tag, cls, value) => { const el=document.createElement(tag); if(cls) el.className=cls; if(value!==undefined) el.textContent=String(value); return el; };
function ui(){ return state.payload?.ui || {}; }
function filteredPages(){
 const q=state.query.trim().toLocaleLowerCase();
 return (state.payload?.pages||[]).filter(page=>{
  if(state.category && page.category!==state.category) return false;
  if(!q) return true;
  const hay=[page.title,page.summary,page.category,...(page.sections||[]).flatMap(s=>[s.heading,s.body,...(s.bullets||[])])].join(' ').toLocaleLowerCase();
  return hay.includes(q);
 });
}
function renderArticle(page){
 const article=byId('documentationArticle'); article.replaceChildren();
 if(!page){article.append(node('p','muted',ui().no_content||'Select a document.'));return;}
 article.append(node('h3','documentation-article-title',page.title));
 article.append(node('p','documentation-summary',page.summary));
 for(const section of page.sections||[]){
  const block=node('section','documentation-section');
  block.append(node('h4','',section.heading));
  if(section.body) block.append(node('p','',section.body));
  if(Array.isArray(section.bullets)&&section.bullets.length){
   const list=node('ul','documentation-bullets');
   for(const item of section.bullets) list.append(node('li','',item));
   block.append(list);
  }
  article.append(block);
 }
}
function renderIndex(){
 const index=byId('documentationIndex'); index.replaceChildren();
 const pages=filteredPages();
 if(!pages.length){index.append(node('p','muted',ui().empty||'No documents found.'));renderArticle(null);return;}
 for(const page of pages){
  const button=node('button','documentation-index-item');
  button.type='button'; button.setAttribute('data-doc-id',page.id);
  if(page.id===state.selected) button.setAttribute('aria-current','page');
  button.append(node('strong','',page.title),node('small','',page.category),node('span','',page.summary));
  button.addEventListener('click',()=>{state.selected=page.id;renderIndex();renderArticle(page);});
  index.append(button);
 }
 const active=pages.find(p=>p.id===state.selected)||pages[0];
 state.selected=active.id; renderArticle(active);
}
function renderSources(){
 const list=byId('documentationSources'); list.replaceChildren();
 for(const source of state.payload?.source_register||[]) list.append(node('li','',source));
}
function applyUi(){
 const t=ui();
 byId('documentationTitle').textContent=t.title||'Documentation';
 byId('documentationIntro').textContent=t.intro||'';
 byId('documentationSearchLabel').textContent=t.search_label||'Search';
 byId('documentationSearch').placeholder=t.search_placeholder||'';
 byId('documentationCategoryLabel').textContent=t.category_label||'Category';
 byId('documentationSafety').textContent=t.read_only||'READ ONLY';
 byId('documentationSourcesTitle').textContent=t.sources||'Source register';
 byId('documentationDisclaimer').textContent=t.disclaimer||'';
 const category=byId('documentationCategory'); category.replaceChildren();
 const all=node('option','',t.all_categories||'All categories'); all.value=''; category.append(all);
 const categories=[...new Set((state.payload?.pages||[]).map(p=>p.category))];
 for(const value of categories){const option=node('option','',value);option.value=value;category.append(option);}
 category.value=state.category;
 byId('documentationStatus').textContent=(t.version||'Version')+' '+state.payload.version+' · '+(t.updated||'Updated')+' '+state.payload.updated_at+' · '+(t.editorial_note||'');
 byId('documentationSearch').value=state.query;
}
async function loadDocumentation(){
 const status=byId('documentationStatus');
 status.textContent=STATUS_COPY[language()].loading;
 try{
  const response=await fetch('/api/documentation?lang='+encodeURIComponent(language()),{cache:'no-store',credentials:'same-origin',headers:{'Accept':'application/json'}});
  const payload=await response.json();
  if(!response.ok || payload.schema!=='hes.documentation_response.v1' || payload.language!==language() || JSON.stringify(payload.safety)!==JSON.stringify(safetyExpected) || !Array.isArray(payload.pages) || payload.pages.length<10) throw new Error('Documentation contract validation failed');
  const ids=payload.pages.map(p=>p.id);
  if(new Set(ids).size!==ids.length || payload.pages.some(p=>!p.title || !p.summary || !Array.isArray(p.sections) || !p.sections.length)) throw new Error('Documentation content validation failed');
  state.payload=payload; state.selected=payload.pages.some(p=>p.id===state.selected)?state.selected:payload.pages[0].id;
  state.category=''; applyUi(); renderIndex(); renderSources();
 }catch(error){
  state.payload=null; byId('documentationIndex').replaceChildren(node('p','muted','Documentation unavailable · '+error.message));
  byId('documentationArticle').replaceChildren(node('p','muted','No unverified or stale documentation is shown.'));
  status.textContent='BLOCKED · '+STATUS_COPY[language()].blocked;
 }
}
byId('documentationSearch')?.addEventListener('input',event=>{state.query=event.target.value;renderIndex();});
byId('documentationCategory')?.addEventListener('change',event=>{state.category=event.target.value;renderIndex();});
byId('languageSelect')?.addEventListener('change',()=>{state.selected=null;state.category='';loadDocumentation();});
loadDocumentation();
})();