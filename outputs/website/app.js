(() => {
  "use strict";
  const DATA = window.REPLICATION_DATA;
  const researchers = DATA.researchers;
  const edges = DATA.edges;
  const byName = new Map(researchers.map(d => [d.person, d]));
  const $ = sel => document.querySelector(sel);
  const $$ = sel => [...document.querySelectorAll(sel)];

  const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const compact = n => n == null ? "—" : Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
  const unique = values => [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b));
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const careerColors = {
    "established giant": "var(--accent)",
    "current leader": "var(--teal)",
    "rising/recent leader": "var(--gold)",
    "additional requested researcher": "var(--violet)"
  };
  const continentColors = { "North America":"var(--blue)", "Europe":"var(--teal)", "Asia":"var(--accent)", "Oceania":"var(--gold)" };

  function switchView(id) {
    $$(".view").forEach(v => v.classList.toggle("is-active", v.id === id));
    $$(".nav-link").forEach(v => v.classList.toggle("is-active", v.dataset.view === id));
    history.replaceState(null, "", `#${id}`);
    window.scrollTo({top: 0, behavior: "smooth"});
    if (id === "network") requestAnimationFrame(drawNetwork);
    if (id === "methods") requestAnimationFrame(drawImpactScatter);
  }
  $$("[data-view]").forEach(b => b.addEventListener("click", () => switchView(b.dataset.view)));
  $$("[data-go]").forEach(b => b.addEventListener("click", () => switchView(b.dataset.go)));

  const storedTheme = localStorage.getItem("replication-atlas-theme");
  if (storedTheme) document.documentElement.dataset.theme = storedTheme;
  $("#themeToggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("replication-atlas-theme", next);
    drawHero();
    if ($("#network").classList.contains("is-active")) drawNetwork(true);
    if ($("#methods").classList.contains("is-active")) drawImpactScatter();
  });

  function drawHero() {
    const svg = d3.select("#heroHelix");
    svg.selectAll("*").remove();
    const points = d3.range(34).map(i => {
      const y = 25 + i * 12.2;
      const phase = i * .56;
      return {i, y, x1: 260 + Math.sin(phase) * 122, x2: 260 - Math.sin(phase) * 122, z: Math.cos(phase)};
    });
    svg.append("path").attr("d", d3.line().curve(d3.curveCatmullRom)(points.map(d => [d.x1,d.y])))
      .attr("fill","none").attr("stroke", css("--accent")).attr("stroke-width",3).attr("opacity",.82);
    svg.append("path").attr("d", d3.line().curve(d3.curveCatmullRom)(points.map(d => [d.x2,d.y])))
      .attr("fill","none").attr("stroke", css("--teal")).attr("stroke-width",3).attr("opacity",.76);
    svg.selectAll("line.rung").data(points.filter((d,i)=>i%2===0)).join("line")
      .attr("x1",d=>d.x1).attr("x2",d=>d.x2).attr("y1",d=>d.y).attr("y2",d=>d.y)
      .attr("stroke",css("--line")).attr("stroke-width",1.1).attr("opacity",d=>.35+Math.abs(d.z)*.45);
    svg.selectAll("circle.a").data(points).join("circle").attr("cx",d=>d.x1).attr("cy",d=>d.y).attr("r",d=>3.5+d.z*1.2).attr("fill",css("--accent"));
    svg.selectAll("circle.b").data(points).join("circle").attr("cx",d=>d.x2).attr("cy",d=>d.y).attr("r",d=>3.5-d.z*1.2).attr("fill",css("--teal"));
    const annotations = [{x:60,y:82,t:"INITIATION"},{x:365,y:201,t:"FORK DYNAMICS"},{x:55,y:344,t:"GENOME STABILITY"}];
    const g=svg.selectAll("g.ann").data(annotations).join("g").attr("class","ann").attr("transform",d=>`translate(${d.x},${d.y})`);
    g.append("line").attr("x1",0).attr("x2",66).attr("stroke",css("--line"));
    g.append("text").attr("y",-7).text(d=>d.t).attr("fill",css("--muted")).attr("font-size",10).attr("letter-spacing",".13em");
  }

  function initOverview() {
    $("#metricResearchers").textContent = DATA.meta.researcherCount;
    $("#metricCountries").textContent = unique(researchers.map(d=>d.country)).length;
    $("#metricEdges").textContent = DATA.meta.edgeCount;
    $("#metricMethods").textContent = unique(researchers.flatMap(d=>d.techniques)).length;
    const continents = d3.rollups(researchers, v=>v.length, d=>d.continent).sort((a,b)=>b[1]-a[1]);
    const max = d3.max(continents,d=>d[1]);
    $("#continentChart").innerHTML = continents.map(([name,count]) => `<div class="continent-row"><span>${escapeHtml(name)}</span><div class="continent-track"><i style="width:${count/max*100}%"></i></div><strong>${count}</strong></div>`).join("");
    const top = researchers.filter(d=>d.rank).slice(0,5);
    $("#topLeaders").innerHTML = top.map(d=>`<li data-person="${escapeHtml(d.person)}"><span class="leader-rank">${String(d.rank).padStart(2,"0")}</span><span><span class="leader-name">${escapeHtml(d.person)}</span><span class="leader-lab">${escapeHtml(d.affiliation)}</span></span><span class="leader-score">${d.combined_impact_score_0_100.toFixed(1)}</span></li>`).join("");
    $$("#topLeaders li").forEach(el=>el.addEventListener("click",()=>openProfile(el.dataset.person)));
  }

  const filterState = {search:"",continent:"",career:"",technique:"",subfield:"",sort:"rank"};
  function fillSelect(id, values) {
    const el=$(id);
    values.forEach(v=>el.insertAdjacentHTML("beforeend",`<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`));
  }
  function initDirectory() {
    fillSelect("#continentFilter", unique(researchers.map(d=>d.continent)));
    fillSelect("#careerFilter", unique(researchers.map(d=>d.career_impact_category)));
    fillSelect("#techniqueFilter", unique(researchers.flatMap(d=>d.techniques)));
    fillSelect("#subfieldFilter", unique(researchers.flatMap(d=>d.subfields)));
    $("#researcherSearch").addEventListener("input",e=>{filterState.search=e.target.value.toLowerCase().trim();renderDirectory();});
    [["#continentFilter","continent"],["#careerFilter","career"],["#techniqueFilter","technique"],["#subfieldFilter","subfield"],["#sortResearchers","sort"]].forEach(([id,key])=>$(id).addEventListener("change",e=>{filterState[key]=e.target.value;renderDirectory();}));
    $("#clearFilters").addEventListener("click",()=>{
      Object.assign(filterState,{search:"",continent:"",career:"",technique:"",subfield:"",sort:"rank"});
      $("#researcherSearch").value=""; ["#continentFilter","#careerFilter","#techniqueFilter","#subfieldFilter"].forEach(id=>$(id).value=""); $("#sortResearchers").value="rank"; renderDirectory();
    });
    renderDirectory();
  }
  function renderDirectory() {
    const q=filterState.search;
    let rows=researchers.filter(d=>(!q || [d.person,d.affiliation,d.city,d.country,d.technique_expertise,d.replication_expertise_subfield,d.technique_details,d.replication_expertise_details].join(" ").toLowerCase().includes(q)) && (!filterState.continent || d.continent===filterState.continent) && (!filterState.career || d.career_impact_category===filterState.career) && (!filterState.technique || d.techniques.includes(filterState.technique)) && (!filterState.subfield || d.subfields.includes(filterState.subfield)));
    const sorters={rank:(a,b)=>(a.rank??999)-(b.rank??999),recent:(a,b)=>(b.impact_2021_2026_score_0_100??-1)-(a.impact_2021_2026_score_0_100??-1),name:(a,b)=>a.person.localeCompare(b.person),country:(a,b)=>a.country.localeCompare(b.country)||a.person.localeCompare(b.person)};
    rows.sort(sorters[filterState.sort]);
    $("#resultCount").textContent=`${rows.length} researcher${rows.length===1?"":"s"}`;
    $("#researcherGrid").innerHTML=rows.length?rows.map(cardTemplate).join(""):`<div class="empty-state"><strong>No matching researchers</strong><p>Try removing a filter or broadening the search.</p></div>`;
    $$(".researcher-card").forEach(card=>card.addEventListener("click",()=>openProfile(card.dataset.person)));
  }
  function cardTemplate(d) {
    const rank=d.rank?`#${d.rank}`:"Added";
    const score=d.combined_impact_score_0_100==null?"Unranked":`${d.combined_impact_score_0_100.toFixed(1)} impact`;
    const tags=[...d.subfields.slice(0,2),...d.techniques.slice(0,1)];
    return `<button class="researcher-card" data-person="${escapeHtml(d.person)}"><span class="card-top"><span class="rank-badge">${rank}</span><span class="score-badge">${score}</span></span><h3>${escapeHtml(d.person)}</h3><p class="affiliation">${escapeHtml(d.affiliation)}</p><span class="tag-row">${tags.map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join("")}</span><span class="card-meta"><span>${escapeHtml(d.city)}, ${escapeHtml(d.country)}</span><span>${escapeHtml(d.career_impact_category)}</span></span></button>`;
  }

  function listHtml(items, parser=x=>escapeHtml(x), empty="No indexed entries available") { return items?.length?`<ul class="profile-list">${items.map(x=>`<li>${parser(x)}</li>`).join("")}</ul>`:`<p class="profile-caveat">${empty}</p>`; }
  function paperHtml(text) {
    const match=text.match(/(https?:\/\/[^)\s]+)\)?$/);
    if(!match) return escapeHtml(text);
    const clean=text.replace(match[1],"").replace(/;\s*\)$/, ")").replace(/[;\s]+$/,"");
    return `<a href="${escapeHtml(match[1])}" target="_blank" rel="noopener">${escapeHtml(clean)} ↗</a>`;
  }
  function openProfile(name) {
    const d=byName.get(name); if(!d)return;
    const rank=d.rank?`#${d.rank}`:"Unranked addition";
    $("#profileContent").innerHTML=`<article class="profile-inner"><p class="eyebrow">${escapeHtml(d.career_impact_category)} · ${rank}</p><h2>${escapeHtml(d.person)}</h2><p class="profile-location">${escapeHtml(d.affiliation)} · ${escapeHtml(d.city)}, ${escapeHtml(d.country)}</p><div class="profile-score-row"><div><strong>${d.combined_impact_score_0_100?.toFixed(1)??"—"}</strong><span>Combined impact</span></div><div><strong>${d.lifetime_impact_score_0_100?.toFixed(1)??"—"}</strong><span>Lifetime impact</span></div><div><strong>${d.impact_2021_2026_score_0_100?.toFixed(1)??"—"}</strong><span>2021–2026 impact</span></div></div><div class="profile-columns"><div><section class="profile-section"><h3>Replication areas</h3><div class="tag-row">${d.subfields.map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join("")}</div><p class="profile-caveat">Detailed focus: ${escapeHtml(d.replication_expertise_details)}</p></section><section class="profile-section"><h3>Technique categories</h3><div class="tag-row">${d.techniques.map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join("")}</div><p class="profile-caveat">Detailed methods: ${escapeHtml(d.technique_details)}</p></section><section class="profile-section"><h3>Recent collaborators</h3>${listHtml(d.top_5_collaborators_2021_2026_list)}</section></div><div><section class="profile-section"><h3>Five most recent lab papers</h3>${listHtml(d.five_most_recent_lab_papers_list,paperHtml)}<p class="profile-caveat">${escapeHtml(d.recent_lab_paper_evidence)}</p></section><section class="profile-section"><h3>Most-cited papers from 2021–2026</h3>${listHtml(d.top_5_papers_2021_2026_list,paperHtml)}</section><section class="profile-section"><h3>Top papers, all time</h3>${listHtml(d.top_5_papers_all_time_list,paperHtml)}</section></div></div><section class="profile-section"><h3>Potential future leaders / trainee candidates</h3>${listHtml(d.top_5_trainees_or_future_leaders_list)}<p class="profile-caveat">${escapeHtml(d.trainee_evidence_type)}</p></section><section class="profile-section"><h3>Sources and researcher links</h3><div class="profile-sources"><a href="${escapeHtml(d.lab_website_url)}" target="_blank" rel="noopener">Lab / institution ↗</a><a href="${escapeHtml(d.google_scholar_url)}" target="_blank" rel="noopener">Google Scholar search ↗</a><a href="${escapeHtml(d.author_source_url)}" target="_blank" rel="noopener">OpenAlex profile ↗</a><a href="${escapeHtml(d.affiliation_source_url)}" target="_blank" rel="noopener">Affiliation source ↗</a>${d.orcid?`<a href="${escapeHtml(d.orcid)}" target="_blank" rel="noopener">ORCID ↗</a>`:""}</div><p class="profile-caveat">Lab link: ${escapeHtml(d.lab_website_link_type)}. Scholar link: ${escapeHtml(d.google_scholar_link_type)}.</p><p class="profile-caveat">${escapeHtml(d.source_notes)}</p></section></article>`;
    $("#profileDialog").showModal();
  }
  $("#closeDialog").addEventListener("click",()=>$("#profileDialog").close());
  $("#profileDialog").addEventListener("click",e=>{if(e.target===$("#profileDialog"))$("#profileDialog").close();});

  let networkSimulation=null, networkDrawn=false;
  function colorMap(mode) { return mode==="career"?careerColors:continentColors; }
  function drawNetwork(force=false) {
    const wrap=$(".network-canvas-wrap"), width=wrap.clientWidth, height=wrap.clientHeight;
    if(!width||!height)return;
    if(networkDrawn&&!force){ networkSimulation?.alpha(.2).restart(); return; }
    networkDrawn=true; networkSimulation?.stop();
    const svg=d3.select("#networkSvg"); svg.selectAll("*").remove(); svg.attr("viewBox",`0 0 ${width} ${height}`);
    const root=svg.append("g");
    const nodes=researchers.map(d=>({...d})); const links=edges.map(d=>({...d}));
    const score=d3.scaleSqrt().domain([0,d3.max(nodes,d=>d.combined_impact_score_0_100||18)]).range([6,15]);
    const linkWidth=d3.scaleSqrt().domain([1,d3.max(links,d=>d.weight_recent_shared_papers)]).range([1,6]);
    const link=root.append("g").selectAll("line").data(links).join("line").attr("stroke",css("--muted")).attr("stroke-opacity",.32).attr("stroke-width",d=>linkWidth(d.weight_recent_shared_papers)).style("cursor","pointer");
    const node=root.append("g").selectAll("g").data(nodes).join("g").style("cursor","pointer").attr("tabindex",0).attr("role","button").attr("aria-label",d=>`Open ${d.person} profile`);
    node.append("circle").attr("r",d=>score(d.combined_impact_score_0_100||18)).attr("fill",d=>networkColor(d)).attr("stroke",css("--surface")).attr("stroke-width",2);
    node.append("text").attr("x",d=>d.x>width*.72?-score(d.combined_impact_score_0_100||18)-4:score(d.combined_impact_score_0_100||18)+4).attr("text-anchor",d=>d.x>width*.72?"end":"start").attr("y",4).text(d=>d.person).attr("fill",css("--ink")).attr("font-size",10).attr("display",$("#labelToggle").checked?null:"none").style("pointer-events","none");
    const simulation=d3.forceSimulation(nodes).force("link",d3.forceLink(links).id(d=>d.person).distance(d=>65+Math.max(0,5-d.weight_recent_shared_papers)*8).strength(.35)).force("charge",d3.forceManyBody().strength(-115)).force("center",d3.forceCenter(width/2,height/2)).force("x",d3.forceX(width/2).strength(.035)).force("y",d3.forceY(height/2).strength(.035)).force("collision",d3.forceCollide().radius(d=>score(d.combined_impact_score_0_100||18)+12)).on("tick",()=>{nodes.forEach(d=>{d.x=Math.max(24,Math.min(width-24,d.x));d.y=Math.max(24,Math.min(height-24,d.y));});link.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);node.attr("transform",d=>`translate(${d.x},${d.y})`);node.select("text").attr("x",d=>d.x>width*.72?-score(d.combined_impact_score_0_100||18)-4:score(d.combined_impact_score_0_100||18)+4).attr("text-anchor",d=>d.x>width*.72?"end":"start");});
    networkSimulation=simulation;
    node.call(d3.drag().on("start",(event,d)=>{if(!event.active)simulation.alphaTarget(.2).restart();d.fx=d.x;d.fy=d.y;}).on("drag",(event,d)=>{d.fx=event.x;d.fy=event.y;}).on("end",(event,d)=>{if(!event.active)simulation.alphaTarget(0);d.fx=null;d.fy=null;}));
    svg.call(d3.zoom().scaleExtent([.45,4]).on("zoom",event=>root.attr("transform",event.transform)));
    node.on("click",(_,d)=>inspectNode(d)).on("dblclick",(_,d)=>openProfile(d.person)).on("keydown",(e,d)=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();inspectNode(d);}}).on("mousemove",(e,d)=>showTooltip(e,`${d.person}<br>${d.affiliation}`)).on("mouseleave",hideTooltip);
    link.on("click",(_,d)=>inspectEdge(d)).on("mousemove",(e,d)=>showTooltip(e,`${d.source.person} × ${d.target.person}<br>${d.weight_recent_shared_papers} shared paper${d.weight_recent_shared_papers===1?"":"s"}`)).on("mouseleave",hideTooltip);
    renderNetworkLegend();
  }
  function networkColor(d){const mode=$("#networkColor").value;return (mode==="career"?careerColors[d.career_impact_category]:continentColors[d.continent])||"var(--muted)";}
  function renderNetworkLegend(){const mode=$("#networkColor").value, map=colorMap(mode);$("#networkLegend").innerHTML=Object.entries(map).map(([k,v])=>`<div class="legend-item"><i class="legend-dot" style="background:${v}"></i><span>${escapeHtml(k)}</span></div>`).join("");}
  function inspectNode(d){$("#networkInspector").innerHTML=`<p class="section-kicker">Researcher</p><h2>${escapeHtml(d.person)}</h2><p>${escapeHtml(d.affiliation)}<br>${escapeHtml(d.city)}, ${escapeHtml(d.country)}</p><div class="inspector-score"><div><strong>${d.rank?`#${d.rank}`:"—"}</strong><span>Rank</span></div><div><strong>${d.combined_impact_score_0_100?.toFixed(1)??"—"}</strong><span>Impact</span></div><div><strong>${edges.filter(e=>e.source===d.person||e.target===d.person).length}</strong><span>Roster links</span></div></div><div class="inspector-tags">${[...d.subfields.slice(0,3),...d.techniques.slice(0,2)].map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join("")}</div><button class="primary-action inspector-link" type="button">Open full profile <span>→</span></button>`;$("#networkInspector .inspector-link").addEventListener("click",()=>openProfile(d.person));}
  function inspectEdge(d){const source=typeof d.source==="string"?d.source:d.source.person,target=typeof d.target==="string"?d.target:d.target.person;$("#networkInspector").innerHTML=`<p class="section-kicker">Recent collaboration</p><h2>${escapeHtml(source)}<br>× ${escapeHtml(target)}</h2><div class="inspector-score"><div><strong>${d.weight_recent_shared_papers}</strong><span>Shared papers</span></div><div><strong>${compact(d.shared_citation_sum)}</strong><span>Combined citations</span></div></div><h3 class="section-kicker">Supporting papers</h3>${d.supporting_papers_list.map(p=>`<div class="edge-paper">${paperHtml(p)}</div>`).join("")}`;}
  $("#networkColor").addEventListener("change",()=>drawNetwork(true));
  $("#labelToggle").addEventListener("change",()=>d3.select("#networkSvg").selectAll("g g text").attr("display",$("#labelToggle").checked?null:"none"));
  $("#resetNetwork").addEventListener("click",()=>drawNetwork(true));

  function showTooltip(e,html){const t=$("#tooltip");t.innerHTML=html;t.style.opacity=1;t.style.left=`${Math.min(innerWidth-280,e.clientX+14)}px`;t.style.top=`${Math.min(innerHeight-80,e.clientY+14)}px`;}
  function hideTooltip(){$("#tooltip").style.opacity=0;}

  let selectedMethod=null;
  function initMethods(){
    const methodCounts=d3.rollups(researchers.flatMap(r=>r.techniques.map(t=>({t,r}))),v=>v.length,d=>d.t).sort((a,b)=>b[1]-a[1]).slice(0,18);
    const max=d3.max(methodCounts,d=>d[1]);
    $("#methodBars").innerHTML=methodCounts.map(([m,n])=>`<button class="method-bar" data-method="${escapeHtml(m)}"><span>${escapeHtml(m)}</span><span class="bar-track"><i style="width:${n/max*100}%"></i></span><strong>${n}</strong></button>`).join("");
    $$(".method-bar").forEach(b=>b.addEventListener("click",()=>selectMethod(b.dataset.method)));
    selectMethod(methodCounts[0][0]);
  }
  function selectMethod(method){selectedMethod=method;$$(".method-bar").forEach(b=>b.classList.toggle("is-active",b.dataset.method===method));const people=researchers.filter(d=>d.techniques.includes(method)).sort((a,b)=>(a.rank??999)-(b.rank??999));$("#methodDetailTitle").textContent=method;$("#methodDetailCopy").textContent=`${people.length} researcher${people.length===1?"":"s"} in this roster use ${method} as a core or supporting approach.`;$("#methodPeople").innerHTML=people.map(d=>`<button class="person-chip" data-person="${escapeHtml(d.person)}"><strong>${escapeHtml(d.person)}</strong><span>${escapeHtml(d.country)} · ${d.rank?`rank ${d.rank}`:"unranked"}</span></button>`).join("");$$("#methodPeople .person-chip").forEach(b=>b.addEventListener("click",()=>openProfile(b.dataset.person)));}

  function drawImpactScatter(){
    const host=$("#impactScatter"),width=host.clientWidth,height=host.clientHeight||520;if(!width)return;host.innerHTML="";
    const margin={top:18,right:24,bottom:58,left:62},w=width-margin.left-margin.right,h=height-margin.top-margin.bottom;
    const svg=d3.select(host).append("svg").attr("viewBox",`0 0 ${width} ${height}`);const g=svg.append("g").attr("transform",`translate(${margin.left},${margin.top})`);
    const data=researchers.filter(d=>d.lifetime_impact_score_0_100!=null&&d.impact_2021_2026_score_0_100!=null);const x=d3.scaleLinear().domain([0,100]).range([0,w]),y=d3.scaleLinear().domain([0,100]).range([h,0]);
    g.append("g").attr("class","grid").attr("transform",`translate(0,${h})`).call(d3.axisBottom(x).ticks(width<600?5:10).tickSize(-h).tickFormat(""));g.append("g").attr("class","grid").call(d3.axisLeft(y).ticks(5).tickSize(-w).tickFormat(""));g.append("g").attr("class","axis").attr("transform",`translate(0,${h})`).call(d3.axisBottom(x));g.append("g").attr("class","axis").call(d3.axisLeft(y));
    svg.append("text").attr("class","axis-label").attr("x",margin.left+w/2).attr("y",height-12).attr("text-anchor","middle").text("Lifetime impact score");svg.append("text").attr("class","axis-label").attr("transform","rotate(-90)").attr("x",-(margin.top+h/2)).attr("y",17).attr("text-anchor","middle").text("2021–2026 impact score");
    g.selectAll("circle").data(data).join("circle").attr("cx",d=>x(d.lifetime_impact_score_0_100)).attr("cy",d=>y(d.impact_2021_2026_score_0_100)).attr("r",d=>d.career_impact_category==="rising/recent leader"?7:5.5).attr("fill",d=>careerColors[d.career_impact_category]).attr("stroke",css("--surface")).attr("stroke-width",1.5).style("cursor","pointer").on("click",(_,d)=>openProfile(d.person)).on("mousemove",(e,d)=>showTooltip(e,`${d.person}<br>Lifetime ${d.lifetime_impact_score_0_100.toFixed(1)} · Recent ${d.impact_2021_2026_score_0_100.toFixed(1)}`)).on("mouseleave",hideTooltip);
  }

  const publicationUpdates=DATA.publicationUpdates||[];
  const publicationUpdateMeta=DATA.publicationUpdateMeta||{};
  const updateState={search:"",status:""};
  function readableDate(value){
    if(!value)return "Date not resolved";
    return new Intl.DateTimeFormat("en",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}).format(new Date(`${value}T00:00:00Z`));
  }
  function updateCard(d){
    const researchers=d.network_researchers||[];
    const people=researchers.map(name=>`<button class="update-person" type="button" data-person="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("");
    const secondary=[];
    if(d.doi)secondary.push(`<a href="${escapeHtml(d.doi)}" target="_blank" rel="noopener">DOI ↗</a>`);
    if(d.pmid)secondary.push(`<a href="${escapeHtml(d.pmid)}" target="_blank" rel="noopener">PubMed ↗</a>`);
    secondary.push(`<a href="${escapeHtml(d.openalex_id)}" target="_blank" rel="noopener">OpenAlex ↗</a>`);
    return `<article class="update-card"><div class="update-meta"><time datetime="${escapeHtml(d.publication_date)}">${readableDate(d.publication_date)}</time><span class="update-status status-${escapeHtml(d.status.toLowerCase().replace(/[^a-z]+/g,"-"))}">${escapeHtml(d.status)}</span></div><h2><a href="${escapeHtml(d.url)}" target="_blank" rel="noopener">${escapeHtml(d.title)} ↗</a></h2><p class="update-venue">${escapeHtml(d.venue)}${d.open_access_status?` · ${escapeHtml(d.open_access_status)} access`:""}</p><div class="update-people" aria-label="Researchers in atlas">${people}</div><div class="update-links">${secondary.join("")}</div></article>`;
  }
  function renderUpdates(){
    const q=updateState.search;
    const rows=publicationUpdates.filter(d=>(!updateState.status||d.status===updateState.status)&&(!q||[d.title,d.venue,...(d.network_researchers||[])].join(" ").toLowerCase().includes(q)));
    const preprints=rows.filter(d=>d.status==="Preprint").length;
    const accepted=rows.filter(d=>d.status==="Accepted manuscript").length;
    $("#updatesSummary").innerHTML=`<div><strong>${rows.length}</strong><span>matching outputs</span></div><div><strong>${preprints}</strong><span>preprints</span></div><div><strong>${accepted}</strong><span>accepted manuscripts detected</span></div>`;
    $("#updateFeed").innerHTML=rows.length?rows.map(updateCard).join(""):`<div class="empty-state"><strong>No matching updates</strong><p>Try removing a status filter or broadening the search.</p></div>`;
    $$("#updateFeed .update-person").forEach(button=>button.addEventListener("click",()=>openProfile(button.dataset.person)));
  }
  function initUpdates(){
    const statuses=unique(publicationUpdates.map(d=>d.status));
    fillSelect("#updatesStatus",statuses);
    $("#updatesSearch").addEventListener("input",event=>{updateState.search=event.target.value.toLowerCase().trim();renderUpdates();});
    $("#updatesStatus").addEventListener("change",event=>{updateState.status=event.target.value;renderUpdates();});
    $("#clearUpdateFilters").addEventListener("click",()=>{updateState.search="";updateState.status="";$("#updatesSearch").value="";$("#updatesStatus").value="";renderUpdates();});
    const generated=publicationUpdateMeta.generated_at;
    if(generated)$("#updatesAsOf").textContent=readableDate(generated);
    if(publicationUpdateMeta.window_start&&publicationUpdateMeta.window_end)$("#updatesWindow").textContent=`OpenAlex · ${readableDate(publicationUpdateMeta.window_start)}–${readableDate(publicationUpdateMeta.window_end)}`;
    renderUpdates();
  }

  drawHero(); initOverview(); initDirectory(); initMethods(); initUpdates();
  const initial=location.hash.slice(1); if(["overview","researchers","network","methods","updates"].includes(initial))switchView(initial);
  let resizeTimer; window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if($("#network").classList.contains("is-active"))drawNetwork(true);if($("#methods").classList.contains("is-active"))drawImpactScatter();},180);});
})();
