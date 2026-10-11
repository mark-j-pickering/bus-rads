(async function(){
const get=p=>fetch(p).then(r=>{if(!r.ok)throw new Error(`${p}: HTTP ${r.status}`);return r.json()});
const list=document.getElementById('list');
const fail=err=>{list.innerHTML=`<p class="error">Couldn't load the map data (${err.message}).</p>`};
let base,index;
try{[base,index]=await Promise.all([get('data/base.json'),get('data/index.json')])}catch(err){fail(err);return}
const DEPOTS=index.depots;

const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const col=g=>css('--g'+g)||'#888';

// Fitting bounds into a zero-size container gives a NaN zoom, so wait until the map has a size
// (e.g. a page opened in a background tab), then keep Leaflet in step with later resizes.
const mapEl=document.getElementById('map');
await new Promise(res=>{if(mapEl.clientWidth&&mapEl.clientHeight)return res();
  const ro=new ResizeObserver(()=>{if(mapEl.clientWidth&&mapEl.clientHeight){ro.disconnect();res()}});ro.observe(mapEl)});
const map=L.map(mapEl,{zoomControl:true,preferCanvas:true,attributionControl:true,zoomSnap:.25,zoomDelta:.5});
new ResizeObserver(()=>map.invalidateSize()).observe(mapEl);
map.attributionControl.setPrefix(false).addAttribution('Data: Translink SEQ GTFS (CC BY 4.0)');
const R=L.canvas({padding:.3});
let L_base,L_zone,L_shared,L_route,L_stops,L_spokes,L_labels,L_hub,hubSpokes=[];
let L_hl=null,L_fp=null,L_rs=null,pinned=null,hover=null;

// The selected depot's data and what's derived from it; replaced by loadDepot().
let depotId=null,zones,cells,rbuf,gbuf,routes,stops,meta;
let fams=[],FAM={},AREA={},PLACES=[],HUBS=[],RG={},ZB=null;
const cache={};
function fetchDepot(id){
  const D=`data/${id}/`;
  return cache[id]||(cache[id]=Promise.all(['zones.geojson','cells.geojson','routebuf.geojson','groupbuf.geojson',
    'routes.geojson','stops.geojson','meta.json'].map(f=>get(D+f))).catch(err=>{delete cache[id];throw err}));
}
// The depot comes from the URL hash (#carina, #all), so a view can be shared; Toowong by default.
function depotFromURL(){
  const want=(location.hash.slice(1)||new URLSearchParams(location.search).get('depot')||'').toLowerCase();
  return (DEPOTS.find(d=>d.id===want)||DEPOTS.find(d=>d.id==='toowong')||DEPOTS[0]).id;
}
async function loadDepot(id){
  if(id===depotId)return;
  let data;
  try{data=await fetchDepot(id)}catch(err){fail(err);return}
  depotId=id;
  [zones,cells,rbuf,gbuf,routes,stops,meta]=data;
  // Families come from the depot config; any group it doesn't list goes under "Other".
  fams=meta.families.map((f,i)=>['f'+i,f.label]);
  FAM={};meta.families.forEach((f,i)=>f.groups.forEach(g=>FAM[g]='f'+i));
  meta.groups.forEach(g=>{if(!FAM[g.group]){FAM[g.group]='other';if(!fams.some(f=>f[0]==='other'))fams.push(['other','Other'])}});
  AREA=meta.areas;PLACES=meta.places;HUBS=meta.hubs;
  RG={};meta.groups.forEach(g=>g.routes.forEach(r=>RG[r]=g.group));
  ZB=L.geoJSON(zones).getBounds();
  if(spokesPreview)map.removeLayer(spokesPreview);
  focus=null;pinned=null;hover=null;hoverFam=null;spokesPreview=null;map.closePopup();
  const label=id==='all'?meta.name:`${meta.name} depot`;
  document.getElementById('eyebrow').textContent=`${label} · weekday`;
  mapEl.setAttribute('aria-label',`Map of ${label} service zones`);
  document.title=`Bus RADS · ${meta.name}`;
  document.getElementById('lSpokes').hidden=!HUBS.length;
  document.getElementById('spokesName').textContent=HUBS.length===1?HUBS[0].short:'Hub';
  document.querySelectorAll('#depotSeg button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.d===id));
  map.fitBounds(ZB,{padding:[16,16]});
  renderList();draw();
}
let focus=null,view='zones',hoverFam=null;
// A hovered legend family previews over the focused group; otherwise only the focused group stays bright.
const dim=g=>hoverFam?(hoverFam.startsWith('hub:')?!HUBS[+hoverFam.slice(4)].groups[g]:FAM[g]!==hoverFam):(focus&&g!==focus);
function draw(){
  [L_base,L_zone,L_shared,L_fp,L_route,L_stops,L_spokes,L_labels,L_hub,L_hl].forEach(l=>l&&map.removeLayer(l));L_hl=null;L_fp=null;
  L_base=L.layerGroup([
    L.geoJSON(base.river,{renderer:R,interactive:false,style:{color:css('--river'),weight:7,opacity:1}}),
    L.geoJSON(base.roads,{renderer:R,interactive:false,style:{color:css('--road'),weight:1.1,opacity:.9}}),
    L.geoJSON(base.rail,{renderer:R,interactive:false,style:{color:css('--rail'),weight:1.6,opacity:.9,dashArray:'5 3'}})
  ]).addTo(map);
  const SH=f=>['shared','cbd'].includes(f.properties.cls);
  L_shared=L.layerGroup([
    L.geoJSON(cells,{renderer:R,interactive:false,filter:SH,style:f=>({stroke:false,fillColor:css(f.properties.cls==='cbd'?'--cbd':'--shared'),fillOpacity:f.properties.cls==='cbd'?.18:.34})}),
    L.geoJSON(zones,{renderer:R,interactive:false,filter:SH,style:{color:css('--shared'),weight:1.6,dashArray:'4 3',fill:false,opacity:.9}})
  ]);
  L_fp=focus?L.geoJSON(gbuf,{renderer:R,interactive:false,filter:f=>f.properties.group===focus,style:f=>({stroke:false,fillColor:col(focus),fillOpacity:f.properties.kind==='main'?.28:.14})}):null;
  L_zone=L.geoJSON(zones,{renderer:R,interactive:false,filter:f=>FAM[f.properties.cls],
    style:f=>{const g=f.properties.cls;return{color:col(g),weight:dim(g)?.5:1.4,fillColor:col(g),fillOpacity:dim(g)?.06:(view==='both'?.28:.45),opacity:dim(g)?.2:.9}}});
  L_route=L.geoJSON(routes,{renderer:R,filter:f=>f.properties.main,
    style:f=>{const g=f.properties.group;return{color:col(g),weight:dim(g)?1:(view==='routes'?3:2.2),opacity:dim(g)?.12:.9}},
    onEachFeature:(f,l)=>{const p=f.properties;l.bindPopup(`<div class="pp"><h3>${p.route_short_name}</h3>${p.name}<div class="m">${p.trips} weekday trips · ${p.group}</div></div>`)}});
  if(view!=='routes'&&document.getElementById('tShared').checked) L_shared.addTo(map);
  if(L_fp) L_fp.addTo(map);
  if(view!=='routes') L_zone.addTo(map);
  if(view!=='zones') L_route.addTo(map);
  L_stops=L.geoJSON(stops,{renderer:R,pointToLayer:(f,ll)=>{const c=f.properties.cls;const k=FAM[c]?col(c):css(c==='hub'?'--hub':'--shared');
      return L.circleMarker(ll,{radius:2.6,color:k,weight:1,fillColor:k,fillOpacity:.9,opacity:(FAM[c]&&dim(c))?.15:.9,group:c})},
    onEachFeature:(f,l)=>l.bindPopup(()=>stopHTML(f.properties,true))});
  if(map.getZoom()>=14) L_stops.addTo(map);
  // hubs + spokes: one spoke per group from its anchor to each hub it visits, width scaled to visits
  hubSpokes=HUBS.map(h=>L.layerGroup(meta.groups.filter(g=>h.groups[g.group]).map(g=>{
    const v=h.groups[g.group];return L.polyline([[g.cy,g.cx],[h.lat,h.lon]],{renderer:R,color:col(g.group),weight:2+Math.sqrt(v)*0.7,opacity:dim(g.group)?.12:.75,lineCap:'round',group:g.group})
      .bindPopup(`<div class="pp"><h3>${g.group} → ${h.short}</h3>${v} weekday stop visits at ${h.name}</div>`)})));
  L_spokes=L.layerGroup(hubSpokes);
  if(HUBS.length&&document.getElementById('tSpokes').checked) L_spokes.addTo(map);
  L_hub=L.layerGroup(HUBS.map(h=>L.circleMarker([h.lat,h.lon],{renderer:R,radius:9,color:css('--panel'),weight:3,fillColor:css('--fg'),fillOpacity:1})
    .bindPopup(`<div class="pp"><h3>${h.name}</h3>Routes ${h.routes.join(', ')}<div class="m">${Object.values(h.groups).reduce((a,b)=>a+b,0)} weekday stop visits</div></div>`))).addTo(map);
  L_labels=L.layerGroup(PLACES.map(([n,la,lo])=>L.marker([la,lo],{opacity:0,interactive:false,icon:L.divIcon({className:'',iconSize:[0,0]})}).bindTooltip(n,{permanent:true,direction:'center',className:'lbl-wrap',opacity:1}).on('add',function(){const t=this.getTooltip();t&&t.getElement()&&t.getElement().classList.add('lbl')})));
  if(document.getElementById('tLabels').checked&&map.getZoom()>=12) L_labels.addTo(map);
  applyHL();
}
// Hover labels: our own hit test on each mouse move, independent of Leaflet's canvas hover state, which got stuck after redraws.
const ztip=L.tooltip({className:'ztip',direction:'right',offset:[14,0],interactive:false});
function hitIn(group,lp){let hit=null;group&&group.eachLayer(l=>{if(!hit&&l._pxBounds&&l._pxBounds.contains(lp)&&l._containsPoint(lp))hit=l});return hit}
function hitZone(ll){const lp=map.latLngToLayerPoint(ll);
  if(L_zone&&map.hasLayer(L_zone)){const h=hitIn(L_zone,lp);if(h)return{zone:h.feature.properties.cls}}
  if(L_shared&&map.hasLayer(L_shared)){const h=hitIn(L_shared.getLayers()[0],lp);if(h)return{cell:h.feature.properties}}
  return null}
function hitStop(ll){const lp=map.latLngToLayerPoint(ll);let best=null,bd=9;
  for(const g of [L_rs,L_stops]){if(!g||!map.hasLayer(g))continue;g.eachLayer(l=>{if(!l._point)return;const d=l._point.distanceTo(lp);if(d<bd){bd=d;best=l}});if(best)break}
  return best?best.feature.properties:null}
function stopHTML(p,click){
  const chips=p.rc.split(' ').filter(Boolean).map(x=>{const [r,n]=x.split(':');return `<${click?'button':'span'} class="tchip${click?' pchip':''}${(pinned||hover)===r?' on':''}" data-r="${r}" style="--c:var(--g${RG[r]})">${r}<small>${n}</small></${click?'button':'span'}>`}).join('');
  return `<div class="sn">${p.stop_name}</div><div class="tchips">${chips}</div>`+(p.other?`<div class="m">Other routes: ${p.other}</div>`:'')+`<div class="m">Serviced ${Math.round(p.ntrips)} times each weekday by these routes${click?' · tap a route to highlight it':''}</div>`}
let hovPending=false,lastMove=null;
map.on('mousemove',e=>{lastMove=e.latlng;if(hovPending)return;hovPending=true;requestAnimationFrame(()=>{hovPending=false;
  let h=null,sp=null;try{sp=hitStop(lastMove);if(!sp)h=hitZone(lastMove)}catch(err){h=null}
  const c=map.getContainer();
  if(sp){ztip.setLatLng(lastMove).setContent(stopHTML(sp,false));if(!map.hasLayer(ztip))ztip.addTo(map);c.style.cursor='pointer';return}
  if(!h){if(map.hasLayer(ztip))map.removeLayer(ztip);c.style.cursor='';return}
  let html;
  if(h.zone){html=`<b>${h.zone}</b>${AREA[h.zone]||''}`;c.style.cursor='pointer'}
  else{const p=h.cell;html=(p.cls==='cbd'?'<b>City</b>all groups pass through':`<b>Shared</b>${p.g.split(' ').map(x=>x.replace(':',' ')+'%').join(' · ')}`)+`<div class="m">Routes ${p.r}</div>`;c.style.cursor=''}
  ztip.setLatLng(lastMove).setContent(html);if(!map.hasLayer(ztip))ztip.addTo(map)})});
map.on('mouseout',()=>{if(map.hasLayer(ztip))map.removeLayer(ztip)});
map.on('click',e=>{if(map._popup&&map.hasLayer(map._popup))return;let h=null;try{h=hitZone(e.latlng)}catch(err){}if(h&&h.zone)setFocus(h.zone)});
function syncStops(){if(!L_stops)return;const show=!(pinned||hover)&&map.getZoom()>=14;show?L_stops.addTo(map):map.removeLayer(L_stops)}
function pinRoute(r){hover=null;pinned=(pinned===r)?null:r;document.querySelectorAll('.chip').forEach(x=>x.setAttribute('aria-pressed',x.dataset.r===pinned));map.closePopup();applyHL();if(pinned)hlBounds(pinned);else if(focus)groupBounds(focus);else goHome()}
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('.pchip');if(b)pinRoute(b.dataset.r)},true);
// Re-apply dimming to the existing layers without rebuilding them (cheap enough for hover).
function restyle(){
  hubSpokes.forEach(hs=>hs.eachLayer(l=>l.setStyle({opacity:dim(l.options.group)?.12:.75})));
  L_stops&&L_stops.eachLayer(l=>FAM[l.options.group]&&l.setStyle({opacity:dim(l.options.group)?.15:.9}));
  applyHL();
}
function applyHL(){
  if(L_hl){map.removeLayer(L_hl);L_hl=null}
  if(L_rs){map.removeLayer(L_rs);L_rs=null}
  if(L_zone)L_zone.resetStyle(); if(L_route)L_route.resetStyle();
  syncStops();
  const r=pinned||hover; if(!r)return;
  const feats=routes.features.filter(f=>f.properties.route_short_name===r); if(!feats.length)return;
  const p=feats[0].properties, fc={type:'FeatureCollection',features:feats};
  L_zone&&L_zone.setStyle({fillOpacity:.08,opacity:.25}); L_route&&L_route.setStyle({opacity:.12});
  let best=[];feats.filter(f=>f.properties.main).forEach(f=>{const c=f.geometry.type==='LineString'?f.geometry.coordinates:f.geometry.coordinates.flat(1);if(c.length>best.length)best=c});
  const mid=best[Math.floor(best.length/2)];
  L_hl=L.layerGroup([
    L.geoJSON(rbuf,{renderer:R,interactive:false,filter:f=>f.properties.route===r,style:f=>({stroke:false,fillColor:col(p.group),fillOpacity:f.properties.kind==='main'?.42:.18})}),
    L.geoJSON(fc,{renderer:R,interactive:false,style:f=>({color:css('--panel'),weight:f.properties.main?9:6,opacity:1,lineCap:'round',lineJoin:'round'})}),
    L.geoJSON(fc,{renderer:R,style:f=>({color:col(p.group),weight:f.properties.main?5:3,dashArray:f.properties.main?null:'6 5',opacity:1,lineCap:'round',lineJoin:'round'}),onEachFeature:(f,l)=>l.bindPopup(`<div class="pp"><h3>${r}${f.properties.main?'':' · variant'}</h3>${p.name}<div class="m">${f.properties.main?p.trips+' weekday trips':f.properties.n+' weekday trips use this path'} · ${p.group}</div></div>`)}),
    L.tooltip({permanent:true,direction:'top',className:'rtip',offset:[0,-6]}).setLatLng([mid[1],mid[0]]).setContent(`<b>${r}</b>${p.name}`)
  ]).addTo(map);
  // only the stops this route actually serves
  L_rs=L.geoJSON(stops,{renderer:R,filter:f=>(' '+f.properties.rc).includes(' '+r+':'),
    pointToLayer:(f,ll)=>L.circleMarker(ll,{radius:3.6,color:css('--panel'),weight:1.5,fillColor:col(p.group),fillOpacity:1}),
    onEachFeature:(f,l)=>l.bindPopup(()=>stopHTML(f.properties,true))}).addTo(map);
}
function hlBounds(r){const b=L.geoJSON({type:'FeatureCollection',features:routes.features.filter(f=>f.properties.route_short_name===r)}).getBounds();if(b.isValid())map.flyToBounds(b,{padding:[40,40],maxZoom:14})}
map.on('zoomend',()=>{ syncStops();
  if(!L_labels)return;
  const on=document.getElementById('tLabels').checked&&map.getZoom()>=12; on?L_labels.addTo(map):map.removeLayer(L_labels)});
// panel
// Collapsed families are remembered per browser, keyed by family label so they carry across depots.
const COLLAPSED_KEY='busrads.collapsed';
const collapsed=new Set((()=>{try{return JSON.parse(localStorage.getItem(COLLAPSED_KEY))||[]}catch(e){return []}})());
function saveCollapsed(){try{localStorage.setItem(COLLAPSED_KEY,JSON.stringify([...collapsed]))}catch(e){}}
// Hub sections start collapsed; which ones are open is remembered per browser, by hub name.
const HUBS_KEY='busrads.hubsOpen';
const hubsOpen=new Set((()=>{try{return JSON.parse(localStorage.getItem(HUBS_KEY))||[]}catch(e){return []}})());
let spokesPreview=null;
const canHover=window.matchMedia('(hover: hover)').matches;
const famLabel=g=>(fams.find(f=>f[0]===FAM[g])||[])[1];
function hubCard(h,i){const open=hubsOpen.has(h.name);const tot=Object.values(h.groups).reduce((a,b)=>a+b,0);const mx=Math.max(...Object.values(h.groups));
  return `<button class="fam hubfam" data-h="${i}" aria-expanded="${open}"><span><i class="chev" aria-hidden="true"></i>${h.name}</span><span>${tot} visits</span></button><div class="hub-body"${open?'':' hidden'}><div class="bars">${Object.entries(h.groups).sort((a,b)=>b[1]-a[1]).map(([g,v])=>`<div class="bar"><span>${g}</span><i style="width:${(v/mx*100).toFixed(0)}%;background:var(--g${g})"></i><span>${v}</span></div>`).join('')}</div><button class="hub-go" data-h="${i}">Show on map</button></div>`}
function renderList(){
  list.innerHTML=HUBS.map(hubCard).join('')+fams.map(([k,lab])=>{const items=meta.groups.filter(g=>FAM[g.group]===k);const t=items.reduce((a,g)=>a+g.trips,0);
    const open=!collapsed.has(lab);
    return `<button class="fam" data-f="${lab}" data-k="${k}" aria-expanded="${open}"><span><i class="chev" aria-hidden="true"></i>${lab}</span><span>${t} trips</span></button><div class="fam-body"${open?'':' hidden'}>`+items.map(g=>`<div class="row${focus===g.group?' on':''}"><button class="grp" data-g="${g.group}" aria-pressed="${focus===g.group}"><i class="sw" style="background:var(--g${g.group})"></i><span class="pfx">${g.group}</span><span class="area">${AREA[g.group]||''}</span><span class="num"><b>${g.trips}</b>trips</span></button><div class="chips">${g.routes.map(r=>`<button class="chip" data-r="${r}" style="--c:var(--g${g.group})" aria-pressed="${pinned===r}" aria-label="Highlight route ${r}">${r}</button>`).join('')}</div></div>`).join('')+'</div>'}).join('');
  // Hovering a family header previews it on the map. Pointer devices only: on touch, a tap
  // would leave the preview stuck on, and tapping already collapses the family.
  if(canHover)list.querySelectorAll('.fam:not(.hubfam)').forEach(b=>{
    b.onmouseenter=()=>{hoverFam=b.dataset.k;restyle()};
    b.onmouseleave=()=>{hoverFam=null;restyle()};});
  list.querySelectorAll('.fam:not(.hubfam)').forEach(b=>b.onclick=()=>{const f=b.dataset.f,k=b.dataset.k;
    if(collapsed.has(f)){collapsed.delete(f);saveCollapsed();renderList();return}
    collapsed.add(f);saveCollapsed();
    // Collapsing a family clears a focused group or pinned route inside it, as if its row or chip were
    // clicked again, so the map never stays highlighted by a control that's folded away.
    const focusIn=focus&&FAM[focus]===k, pinIn=pinned&&FAM[RG[pinned]]===k;
    if(!focusIn&&!pinIn){renderList();return}
    if(focusIn)focus=null;
    if(pinIn){pinned=null;hover=null;map.closePopup()}
    renderList();draw();
    focus?groupBounds(focus):goHome()});
  list.querySelectorAll('.grp').forEach(b=>b.onclick=()=>setFocus(b.dataset.g));
  const chips=[...list.querySelectorAll('.chip')];
  chips.forEach(c=>{const r=c.dataset.r;
    c.onmouseenter=()=>{hover=r;applyHL()};
    c.onmouseleave=()=>{hover=null;applyHL()};
    c.onclick=()=>pinRoute(r);});
  list.querySelectorAll('.hubfam').forEach(b=>{const h=HUBS[+b.dataset.h];
    b.onclick=()=>{hubsOpen.has(h.name)?hubsOpen.delete(h.name):hubsOpen.add(h.name);try{localStorage.setItem(HUBS_KEY,JSON.stringify([...hubsOpen]))}catch(e){}renderList()};
    // Hovering previews the groups that serve this hub, with its spokes even if the toggle is off.
    if(canHover){
      b.onmouseenter=()=>{hoverFam='hub:'+b.dataset.h;const hs=hubSpokes[+b.dataset.h];if(hs&&!map.hasLayer(L_spokes)){hs.addTo(map);spokesPreview=hs}restyle()};
      b.onmouseleave=()=>{hoverFam=null;if(spokesPreview){map.removeLayer(spokesPreview);spokesPreview=null}restyle()};}});
  list.querySelectorAll('.hub-go').forEach(b=>{const h=HUBS[+b.dataset.h];b.onclick=()=>{setFocus(null);map.flyTo([h.lat,h.lon],14)}});
}
function setFocus(g){focus=(focus===g)?null:g;
  if(focus&&collapsed.delete(famLabel(focus)))saveCollapsed();
  renderList();draw();
  if(focus)groupBounds(focus);else goHome();}
function goHome(){map.flyToBounds(ZB,{padding:[16,16]})}
function groupBounds(g){const b=L.geoJSON(routes,{filter:f=>f.properties.group===g}).getBounds();if(b.isValid())map.flyToBounds(b,{padding:[30,30],maxZoom:14})}
const dayText=new Date(index.day+'T00:00').toLocaleDateString('en-AU',{weekday:'long',day:'numeric',month:'long'});
document.getElementById('foot').textContent=`${index.feed}. Trip counts are for ${dayText}. School (7xx) and special (9xx) runs are not in this feed. Basemap drawn from Translink route paths. Unofficial; not affiliated with Brisbane City Council or Translink.`;
const views={vZones:'zones',vRoutes:'routes',vBoth:'both'};
Object.keys(views).forEach(id=>document.getElementById(id).onclick=()=>{view=views[id];Object.keys(views).forEach(k=>document.getElementById(k).setAttribute('aria-pressed',k===id));draw()});
['tSpokes','tShared','tLabels'].forEach(id=>document.getElementById(id).onchange=draw);
const panel=document.getElementById('panel');document.getElementById('sheetTab').onclick=()=>panel.classList.toggle('min');
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
new MutationObserver(draw).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
// depot selector
const seg=document.getElementById('depotSeg');
seg.innerHTML=DEPOTS.map(d=>`<button data-d="${d.id}" aria-pressed="false">${d.id==='all'?'All':d.name}</button>`).join('');
seg.querySelectorAll('button').forEach(b=>b.onclick=()=>{location.hash=b.dataset.d});
window.addEventListener('hashchange',()=>loadDepot(depotFromURL()));
await loadDepot(depotFromURL());
})();
