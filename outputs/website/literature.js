(() => {
  "use strict";
  const data=window.REPLICATION_DATA.literatureTracker||{meta:{},alerts:[],publications:[],latest_ids:[],discovered_ids:[],new_ids:[],by_alert:{}};
  const byId=new Map(data.publications.map(r=>[r.id,r]));
  const byAlert=new Map(data.alerts.map(a=>[a.id,a]));
  const sources={openalex:"OpenAlex",europe_pmc:"Europe PMC / PubMed",biorxiv:"bioRxiv",medrxiv:"medRxiv",crossref:"Crossref"};
  const state={alert:"",search:"",order:"latest",alertSearch:"",alertType:""};
  const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
  const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const safeUrl=u=>/^https?:\/\//i.test(String(u||""))?u:"";
  const dateLabel=value=>value?new Intl.DateTimeFormat("en",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(value.length===10?value+"T00:00:00Z":value)):"Not yet successful";
  const checkLabel=value=>value?new Intl.DateTimeFormat("en",{day:"numeric",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",timeZone:"UTC",timeZoneName:"short"}).format(new Date(value)):"Not yet successful";
  const networkIntro=$("#updatesIntro").textContent;

  function selectFeed(tracker,updateUrl=true){
    $("#networkUpdatesPanel").hidden=tracker;
    $("#literatureTrackerPanel").hidden=!tracker;
    $("#networkUpdatesSnapshot").hidden=tracker;
    $("#updatesIntro").textContent=tracker?"A credential-free literature watchlist across authors and fields, combining public scholarly databases and recent preprints.":networkIntro;
    $("#updatesIntro").closest(".updates-heading").classList.toggle("is-tracker",tracker);
    for(const [id,active] of [["#networkUpdatesTab",!tracker],["#literatureTrackerTab",tracker]]){
      $(id).classList.toggle("is-active",active);$(id).setAttribute("aria-selected",String(active));$(id).tabIndex=active?0:-1;
    }
    window.LITERATURE_TRACKER_ROUTE=tracker?"/literature"+(state.alert?"?alert="+encodeURIComponent(state.alert):""):"";
    if(updateUrl)history.replaceState(null,"","#updates"+window.LITERATURE_TRACKER_ROUTE);
  }
  function selectAlert(id){
    state.alert=byAlert.has(id)?id:"";state.search="";$("#trackerSearch").value="";
    renderAlerts();renderFeed();selectFeed(true);
  }
  function renderAlerts(){
    const rows=data.alerts.filter(a=>(!state.alertSearch||a.name.toLowerCase().includes(state.alertSearch))&&(!state.alertType||(state.alertType==="disabled"?!a.enabled:a.type===state.alertType)));
    $("#trackerAlertList").innerHTML=rows.length?rows.map(a=>`<button type="button" class="tracker-alert ${state.alert===a.id?"is-active":""}" data-alert="${esc(a.id)}" aria-pressed="${state.alert===a.id}"><span>${esc(a.name)}</span><small>${a.enabled?`${a.type==="keyword"?"Topic":"Author"} · ${a.publication_count||0} matches`:esc(a.author?.identity_status==="needs identity review"?"Needs identity review":"Inactive")}</small></button>`).join(""):'<p class="profile-caveat">No alerts match.</p>';
    $$("#trackerAlertList [data-alert]").forEach(b=>b.addEventListener("click",()=>selectAlert(b.dataset.alert)));
  }
  function alertDescription(a){
    if(!a.enabled)return a.disabled_reason;
    if(a.type==="keyword")return `${a.query.title_only?"Title only":"Title / abstract"}: ${a.query.all.join(" AND ")}`;
    return `${a.author.name}${a.author.affiliation?" · "+a.author.affiliation:""} · verified persistent author identity`;
  }
  function card(r){
    const isNew=(data.meta.new_publication_ids||[]).includes(r.id);
    const links=[];
    if(r.doi)links.push(`<a href="https://doi.org/${esc(r.doi)}" target="_blank" rel="noopener">DOI ↗</a>`);
    if(safeUrl(r.preprint_url))links.push(`<a href="${esc(r.preprint_url)}" target="_blank" rel="noopener">Preprint ↗</a>`);
    for(const doi of r.related_publication_dois||[])links.push(`<a href="https://doi.org/${esc(doi)}" target="_blank" rel="noopener">Linked publication ↗</a>`);
    const provenanceNote=r.source_note?`<br>${esc(r.source_note)}`:"";
    return `<article class="update-card tracker-card"><div class="update-meta"><time datetime="${esc(r.publication_date)}">${dateLabel(r.publication_date)}</time><span class="update-status">${esc(r.status)}</span>${isNew?'<span class="tracker-new">Newly found</span>':""}</div><h2><a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">${esc(r.title)} ↗</a></h2><p class="update-venue">${esc(r.venue||"Venue unavailable")}</p><p class="tracker-authors">${esc(r.authors.join(", "))}${r.authors_complete===false?" (roster coauthors only)":""}</p><div class="tracker-badges" aria-label="Matching alerts">${r.alert_ids.filter(id=>byAlert.has(id)).map(id=>`<button type="button" class="update-person" data-alert="${esc(id)}">${esc(byAlert.get(id).name)}</button>`).join("")}</div><p class="tracker-provenance">Found via: ${esc(r.sources.map(s=>sources[s]||s).join(" · "))}${r.enrichment_sources?.length?` · Metadata enriched by: ${esc(r.enrichment_sources.map(s=>sources[s]||s).join(", "))}`:""}<br>First discovered: ${dateLabel(r.first_discovered_at)}${provenanceNote}</p>${r.abstract?`<details class="tracker-abstract"><summary>Abstract</summary><p>${esc(r.abstract)}</p></details>`:""}<div class="update-links">${links.join("")}</div></article>`;
  }
  function renderFeed(){
    const alert=byAlert.get(state.alert);
    let ids=alert?(data.by_alert[alert.id]||[]):state.order==="discovery"?data.discovered_ids:state.order==="new"?data.new_ids:data.latest_ids;
    if(alert&&!alert.enabled)ids=[];
    const rows=ids.map(id=>byId.get(id)).filter(Boolean).filter(r=>!state.search||[r.title,r.venue,r.abstract,...r.authors].join(" ").toLowerCase().includes(state.search));
    $("#trackerOrder").disabled=!!alert;
    $("#trackerSelection").innerHTML=`<h2>${esc(alert?alert.name:state.order==="discovery"?"Latest discoveries":state.order==="new"?"New since previous refresh":"Latest publications")}</h2><p>${esc(alert?alertDescription(alert):"Across all enabled author and topic alerts")}</p><small>${rows.length} shown${alert?` · up to 20 latest of ${alert.publication_count||0} matching records`:" · up to 100"}${data.meta.initial_baseline?" · Initial import is a baseline":""}</small>`;
    $("#trackerFeed").innerHTML=rows.length?rows.map(card).join(""):`<div class="empty-state"><strong>${alert&&!alert.enabled?"Alert inactive":state.order==="new"?"No new discoveries in the latest refresh":"No matching publications"}</strong><p>${esc(alert&&!alert.enabled?alert.disabled_reason:"Results depend on source indexing, the displayed coverage window, and your current filters.")}</p></div>`;
    $$("#trackerFeed [data-alert]").forEach(b=>b.addEventListener("click",()=>selectAlert(b.dataset.alert)));
  }
  function renderHealth(){
    const meta=data.meta, health=Object.values(meta.source_health||{});
    const failures=health.filter(h=>h.status!=="ok");
    const labels=Object.keys(sources).map(source=>{const rows=health.filter(h=>h.source===source),failed=rows.filter(h=>h.status!=="ok").length;return `${sources[source]}: ${!rows.length?"not checked":failed?"partial / failed":"OK"}`;});
    $("#trackerStatus").innerHTML=`<div class="tracker-health-heading"><strong>Refresh: ${esc(meta.refresh_status||"not yet run")}</strong><span>${meta.enabled_alert_count||0} active · ${meta.disabled_alert_count||0} inactive / needs review</span></div><p>Last attempt: ${checkLabel(meta.last_attempt_at)} · Last complete successful check: ${checkLabel(meta.last_successful_check_at)}</p><p>${esc(labels.join(" · "))}</p><p class="profile-caveat">Coverage: ${dateLabel(meta.window_start)}–${dateLabel(meta.window_end)} · ${esc(meta.schedule||"Daily at 06:00 UTC")}</p><p class="profile-caveat">${esc(meta.coverage_note||"")}</p>${failures.length?`<details><summary>Source warnings (${failures.length})</summary><ul>${failures.map(h=>`<li>${esc(sources[h.source]||h.source)}${h.alert_id?" / "+esc(byAlert.get(h.alert_id)?.name||h.alert_id):""}: ${esc(h.error||"Optional metadata enrichment incomplete")}</li>`).join("")}</ul></details>`:""}`;
  }
  $("#networkUpdatesTab").addEventListener("click",()=>selectFeed(false));
  $("#literatureTrackerTab").addEventListener("click",()=>selectFeed(true));
  for(const id of ["#networkUpdatesTab","#literatureTrackerTab"])$(id).addEventListener("keydown",e=>{if(["ArrowLeft","ArrowRight","Home","End"].includes(e.key)){e.preventDefault();const tracker=e.key==="End"||e.key!=="Home"&&id==="#networkUpdatesTab";selectFeed(tracker);$(tracker?"#literatureTrackerTab":"#networkUpdatesTab").focus();}});
  $("#trackerSearch").addEventListener("input",e=>{state.search=e.target.value.toLowerCase().trim();renderFeed();});
  $("#trackerAlertSearch").addEventListener("input",e=>{state.alertSearch=e.target.value.toLowerCase().trim();renderAlerts();});
  $("#trackerAlertType").addEventListener("change",e=>{state.alertType=e.target.value;renderAlerts();});
  $("#trackerOrder").addEventListener("change",e=>{state.order=e.target.value;renderFeed();});
  $("#trackerReset").addEventListener("click",()=>{state.alert="";state.order="latest";state.search="";$("#trackerSearch").value="";$("#trackerOrder").value="latest";renderAlerts();renderFeed();selectFeed(true);});
  const initial=location.hash.slice(1),params=new URLSearchParams(initial.split("?")[1]||"");
  state.alert=byAlert.has(params.get("alert"))?params.get("alert"):"";
  renderAlerts();renderFeed();renderHealth();selectFeed(initial.startsWith("updates/literature"),false);
})();
