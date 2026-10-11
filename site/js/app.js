(async function(){
const DEPOT='toowong';
const get=p=>fetch(p).then(r=>{if(!r.ok)throw new Error(`${p}: HTTP ${r.status}`);return r.json()});
const D=`data/${DEPOT}/`;
let base,zones,cells,rbuf,gbuf,routes,stops,meta;
try{
  [base,zones,cells,rbuf,gbuf,routes,stops,meta]=await Promise.all([
    get('data/base.json'),get(D+'zones.geojson'),get(D+'cells.geojson'),get(D+'routebuf.geojson'),
    get(D+'groupbuf.geojson'),get(D+'routes.geojson'),get(D+'stops.geojson'),get(D+'meta.json')]);
}catch(err){
  document.getElementById('list').innerHTML=`<p class="error">Couldn't load the map data (${err.message}).</p>`;
  return;
}

const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const col=g=>css('--g'+g)||'#888';
// Families come from the depot config; any group it doesn't list goes under "Other".
const fams=meta.families.map((f,i)=>['f'+i,f.label]);
const FAM={};meta.families.forEach((f,i)=>f.groups.forEach(g=>FAM[g]='f'+i));
meta.groups.forEach(g=>{if(!FAM[g.group]){FAM[g.group]='other';if(!fams.some(f=>f[0]==='other'))fams.push(['other','Other'])}});
const AREA=meta.areas, PLACES=meta.places, HUB=meta.hubs[0]||null;

document.getElementById('eyebrow').textContent=`${meta.name} depot · weekday`;
document.getElementById('map').setAttribute('aria-label',`Map of ${meta.name} depot service zones`);
document.title=`Bus RADS · ${meta.name}`;
if(HUB)document.getElementById('spokesName').textContent=HUB.short;
else document.getElementById('lSpokes').hidden=true;

// Fitting bounds into a zero-size container gives a NaN zoom, so wait until the map has a size
// (e.g. a page opened in a background tab), then keep Leaflet in step with later resizes.
const mapEl=document.getElementById('map');
await new Promise(res=>{if(mapEl.clientWidth&&mapEl.clientHeight)return res();
  const ro=new ResizeObserver(()=>{if(mapEl.clientWidth&&mapEl.clientHeight){ro.disconnect();res()}});ro.observe(mapEl)});
const map=L.map(mapEl,{zoomControl:true,preferCanvas:true,attributionControl:true,zoomSnap:.25,zoomDelta:.5});
new ResizeObserver(()=>map.invalidateSize()).observe(mapEl);
const ZB=L.geoJSON(zones).getBounds();
map.fitBounds(ZB,{padding:[16,16]});
map.attributionControl.setPrefix(false).addAttribution('Data: Translink SEQ GTFS (CC BY 4.0)');
const R=L.canvas({padding:.3});
let L_base,L_zone,L_shared,L_route,L_stops,L_spokes,L_labels,L_hub;
let L_hl=null,L_fp=null,L_rs=null,pinned=null,hover=null;
let focus=null,view='zones';
function draw(){
  [L_base,L_zone,L_shared,L_fp,L_route,L_stops,L_spokes,L_labels,L_hub,L_hl].forEach(l=>l&&map.removeLayer(l));L_hl=null;L_fp=null;
  L_base=L.layerGroup([
    L.geoJSON(base.river,{renderer:R,interactive:false,style:{color:css('--river'),weight:7,opacity:1}}),
    L.geoJSON(base.roads,{renderer:R,interactive:false,style:{color:css('--road'),weight:1.1,opacity:.9}}),
    L.geoJSON(base.rail,{renderer:R,interactive:false,style:{color:css('--rail'),weight:1.6,opacity:.9,dashArray:'5 3'}})
  ]).addTo(map);
  const dim=g=>focus&&g!==focus;
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
      return L.circleMarker(ll,{radius:2.6,color:k,weight:1,fillColor:k,fillOpacity:.9,opacity:(FAM[c]&&dim(c))?.15:.9})},
    onEachFeature:(f,l)=>l.bindPopup(()=>stopHTML(f.properties,true))});
  if(map.getZoom()>=14) L_stops.addTo(map);
  // hub + spokes
  L_spokes=L_hub=null;
  if(HUB){
    const h=HUB;
    L_spokes=L.layerGroup(meta.groups.filter(g=>h.groups[g.group]).map(g=>{
      const v=h.groups[g.group];return L.polyline([[g.cy,g.cx],[h.lat,h.lon]],{renderer:R,color:col(g.group),weight:2+Math.sqrt(v)*0.7,opacity:dim(g.group)?.12:.75,lineCap:'round'})
        .bindPopup(`<div class="pp"><h3>${g.group} → ${h.short}</h3>${v} weekday stop visits at ${h.name}</div>`)}));
    if(document.getElementById('tSpokes').checked) L_spokes.addTo(map);
    L_hub=L.circleMarker([h.lat,h.lon],{renderer:R,radius:9,color:css('--panel'),weight:3,fillColor:css('--fg'),fillOpacity:1})
      .bindPopup(`<div class="pp"><h3>${h.name}</h3>Routes ${h.routes.join(', ')}<div class="m">${Object.values(h.groups).reduce((a,b)=>a+b,0)} weekday stop visits</div></div>`).addTo(map);
  }
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
const RG={};meta.groups.forEach(g=>g.routes.forEach(r=>RG[r]=g.group));
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
  const on=document.getElementById('tLabels').checked&&map.getZoom()>=12; on?L_labels.addTo(map):map.removeLayer(L_labels)});
// panel
const list=document.getElementById('list');
function hubCard(){if(!HUB)return '';const h=HUB;const tot=Object.values(h.groups).reduce((a,b)=>a+b,0);const mx=Math.max(...Object.values(h.groups));
  return `<div class="hubcard"><button class="hub-btn" id="hubBtn"><strong>${h.name}</strong><span class="num">${tot} visits/day</span></button><div class="bars">${Object.entries(h.groups).sort((a,b)=>b[1]-a[1]).map(([g,v])=>`<div class="bar"><span>${g}</span><i style="width:${(v/mx*100).toFixed(0)}%;background:var(--g${g})"></i><span>${v}</span></div>`).join('')}</div></div>`}
function renderList(){
  list.innerHTML=hubCard()+fams.map(([k,lab])=>{const items=meta.groups.filter(g=>FAM[g.group]===k);const t=items.reduce((a,g)=>a+g.trips,0);
    return `<div class="fam"><span>${lab}</span><span>${t} trips</span></div>`+items.map(g=>`<div class="row${focus===g.group?' on':''}"><button class="grp" data-g="${g.group}" aria-pressed="${focus===g.group}"><i class="sw" style="background:var(--g${g.group})"></i><span class="pfx">${g.group}</span><span class="area">${AREA[g.group]||''}</span><span class="num"><b>${g.trips}</b>trips</span></button><div class="chips">${g.routes.map(r=>`<button class="chip" data-r="${r}" style="--c:var(--g${g.group})" aria-pressed="${pinned===r}" aria-label="Highlight route ${r}">${r}</button>`).join('')}</div></div>`).join('')}).join('');
  list.querySelectorAll('.grp').forEach(b=>b.onclick=()=>setFocus(b.dataset.g));
  const chips=[...list.querySelectorAll('.chip')];
  chips.forEach(c=>{const r=c.dataset.r;
    c.onmouseenter=()=>{hover=r;applyHL()};
    c.onmouseleave=()=>{hover=null;applyHL()};
    c.onclick=()=>pinRoute(r);});
  if(HUB)document.getElementById('hubBtn').onclick=()=>{setFocus(null);map.flyTo([HUB.lat,HUB.lon],14)};
}
function setFocus(g){focus=(focus===g)?null:g;renderList();draw();
  if(focus)groupBounds(focus);else goHome();}
function goHome(){map.flyToBounds(ZB,{padding:[16,16]})}
function groupBounds(g){const b=L.geoJSON(routes,{filter:f=>f.properties.group===g}).getBounds();if(b.isValid())map.flyToBounds(b,{padding:[30,30],maxZoom:14})}
const dayText=new Date(meta.day+'T00:00').toLocaleDateString('en-AU',{weekday:'long',day:'numeric',month:'long'});
document.getElementById('foot').textContent=`${meta.feed}. Trip counts are for ${dayText}. School (7xx) and special (9xx) runs are not in this feed. Basemap drawn from Translink route paths. Unofficial; not affiliated with Brisbane City Council or Translink.`;
const views={vZones:'zones',vRoutes:'routes',vBoth:'both'};
Object.keys(views).forEach(id=>document.getElementById(id).onclick=()=>{view=views[id];Object.keys(views).forEach(k=>document.getElementById(k).setAttribute('aria-pressed',k===id));draw()});
['tSpokes','tShared','tLabels'].forEach(id=>document.getElementById(id).onchange=draw);
const panel=document.getElementById('panel');document.getElementById('sheetTab').onclick=()=>panel.classList.toggle('min');
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);
new MutationObserver(draw).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
renderList();draw();
})();
