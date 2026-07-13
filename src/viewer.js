import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './viewer.css';
import { MapSettings } from './mapsettings.js';
import TRIPS from '@trips';

const SEASON_COLORS={Winter:"#4a90d9",Spring:"#2fa84f",Summer:"#f0a500",Fall:"#e0701a"};
const CAT_CLASS={"long-haul":"cat-long","regional":"cat-regional","local":"cat-local"};
const LIGHT="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png";
const NOLABELS="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png";
const VOYAGER="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png";
const ATTR='© OpenStreetMap © CARTO';
const CATS=[["long-haul","Long-haul · ≥300 km from home"],
            ["regional","Regional · 75–300 km"],["local","Local · <75 km"]];

function fmtDur(t){return t.duration_days>=1
  ? {v:t.duration_days.toFixed(1),u:'days'} : {v:(t.duration_days*24).toFixed(0),u:'hours'};}
function boundsOf(t){const b=L.latLngBounds([]);
  t.lines.forEach(l=>l.forEach(p=>b.extend([p[0],p[1]])));return b;}

/* ---------- build the LIST view ---------- */
const lv=document.getElementById('listview');
lv.innerHTML=`<div class="lhead"><h1>Timeline Road Trips</h1>
  <p>${TRIPS.length} sampled drives · GPS projected onto OSM roads · click a trip for the full map</p></div>`;
const miniInits=[];
CATS.forEach(([cat,label])=>{
  const trips=TRIPS.map((t,i)=>[t,i]).filter(([t])=>t.category===cat);
  if(!trips.length)return;
  const h=document.createElement('div');h.className='catgroup';h.textContent=label;lv.appendChild(h);
  trips.forEach(([t,i])=>{
    const dur=fmtDur(t);
    const card=document.createElement('div');
    card.className='card '+CAT_CLASS[cat];
    card.onclick=()=>openDetail(i);
    card.innerHTML=`
      <div class="mini" id="mini${i}"><div class="lb">road path</div></div>
      <div class="info">
        <div class="chips">
          <span class="chip">${cat}</span>
          <span class="season" style="background:${SEASON_COLORS[t.season]}">${t.season}</span>
          <span class="cdate">${t.date_label||''}</span>
        </div>
        <h2>${t.title}</h2>
        <div class="facts">
          <div class="fact"><div class="k">Distance</div><div class="v">${t.drive_km.toLocaleString()} <small>km · ${t.drive_mi.toLocaleString()} mi</small></div></div>
          <div class="fact"><div class="k">Avg speed</div><div class="v">${t.avg_speed_kmh} <small>km/h</small></div></div>
          <div class="fact"><div class="k">Duration</div><div class="v">${dur.v} <small>${dur.u}</small></div></div>
          <div class="fact"><div class="k">Stops</div><div class="v">${t.n_stops} <small>${t.n_overnight} overnight</small></div></div>
          <div class="fact"><div class="k">Farthest</div><div class="v">${t.max_dist_from_home_km.toLocaleString()} <small>km</small></div></div>
        </div>
      </div>
      <div class="go">&#8250;</div>`;
    lv.appendChild(card);
    miniInits.push([i,t]);
  });
});
// init the low-detail mini-maps (non-interactive)
miniInits.forEach(([i,t])=>{
  const m=L.map('mini'+i,{zoomControl:false,attributionControl:false,dragging:false,
    scrollWheelZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false,
    tap:false,touchZoom:false,inertia:false});
  // minis follow the shared basemap + opacity but stay label-free for a clean look
  MapSettings.manage(m,{maxZoom:14,forceLabels:false});
  t.lines.forEach(line=>L.polyline(line.map(p=>[p[0],p[1]]),
    {color:'#1a73ff',weight:2.6,opacity:.95,lineJoin:'round'}).addTo(m));
  const b=boundsOf(t);
  if(b.isValid())m.fitBounds(b,{padding:[20,20]});
});

/* ---------- DETAIL view ---------- */
let map=null,preview=null,mainLayers=[],prevLayers=[],curBounds=null,
    animPaths=[],dotsLayer=null,current=null;
let UNIT=localStorage.getItem('rt_unit')||'km';
function initDetail(){
  map=L.map('map',{zoomControl:false,attributionControl:true}).setView([43,-77],6);
  L.control.zoom({position:'topright'}).addTo(map);
  MapSettings.manage(map,{maxZoom:19});   // basemap governed by shared Map settings
  preview=L.map('preview',{zoomControl:false,attributionControl:false,dragging:false,
    scrollWheelZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false,tap:false}).setView([43,-77],5);
  L.tileLayer(VOYAGER,{subdomains:'abcd',maxZoom:12,attribution:ATTR}).addTo(preview);
  map.on('zoomend',animatePaths);
}
function clearD(){
  animPaths.forEach(el=>{if(el._anim)el._anim.cancel();});
  mainLayers.forEach(l=>map.removeLayer(l));prevLayers.forEach(l=>preview.removeLayer(l));
  mainLayers=[];prevLayers=[];animPaths=[];hideDots();}
function stat(k,v,u){return `<div class="stat"><div class="k">${k}</div>
  <div class="v">${v} <span class="u">${u||''}</span></div></div>`;}
function fmtNum(x){return x.toLocaleString(undefined,{maximumFractionDigits:1});}
function unitDist(km){return UNIT=='mi'?{v:fmtNum(km/1.609),u:'mi'}:{v:fmtNum(km),u:'km'};}
function unitSpeed(t){return UNIT=='mi'?{v:t.avg_speed_mph,u:'mph'}:{v:t.avg_speed_kmh,u:'km/h'};}
function setUnit(u){UNIT=u;localStorage.setItem('rt_unit',u);if(current)describe(current);}
/* the bright stroke sweeps start->end over a faint base, showing direction */
function animatePaths(){
  animPaths.forEach(el=>{
    if(!el||!el.getTotalLength)return;
    let len=0;try{len=el.getTotalLength();}catch(e){return;}
    if(!len)return;
    el.style.strokeDasharray=len+' '+len;
    if(el._anim)el._anim.cancel();
    const dur=Math.min(22000,Math.max(7000,len*16));   // slow, ~constant visual speed
    el._anim=el.animate([{strokeDashoffset:len},{strokeDashoffset:-len}],
      {duration:dur,iterations:Infinity,easing:'linear'});
  });
}
function showDots(){
  if(!map||!current)return;hideDots();
  dotsLayer=L.layerGroup();
  (current.raw_lines||current.lines).forEach(line=>line.forEach(p=>
    L.circleMarker([p[0],p[1]],{radius:2.4,weight:0,fillColor:'#1a73ff',fillOpacity:.8})
      .addTo(dotsLayer)));
  dotsLayer.addTo(map);
}
function hideDots(){if(dotsLayer){map.removeLayer(dotsLayer);dotsLayer=null;}}
function draw(t){
  clearD();current=t;
  curBounds=L.latLngBounds([]);
  t.lines.forEach(line=>{
    const pts=line.map(p=>[p[0],p[1]]);pts.forEach(p=>curBounds.extend(p));
    mainLayers.push(L.polyline(pts,{color:'#fff',weight:7,opacity:.8,lineJoin:'round',lineCap:'round'}).addTo(map));
    mainLayers.push(L.polyline(pts,{color:'#1a73ff',weight:4,opacity:.24,lineJoin:'round',lineCap:'round'}).addTo(map));
    const flow=L.polyline(pts,{color:'#1a73ff',weight:4.5,opacity:.98,
      className:'trip-flow',lineJoin:'round',lineCap:'round'}).addTo(map);
    mainLayers.push(flow);animPaths.push(flow._path);
    prevLayers.push(L.polyline(pts,{color:'#1a73ff',weight:2.6,opacity:.9}).addTo(preview));
  });
  t.stops.forEach(s=>{const on=s.overnight;
    mainLayers.push(L.circleMarker([s.lat,s.lng],{radius:on?6:4,color:'#fff',weight:on?2:1.4,
      fillColor:on?'#1a73ff':'#8a9099',fillOpacity:1})
      .bindPopup(`<b>${s.label}</b><br>${s.type}<br>${on?'overnight':s.dwell_hours+' h'}`).addTo(map));});
  describe(t);
}
function describe(t){
  document.getElementById('title').textContent=t.title;
  const sb=document.getElementById('season');sb.textContent=t.season;sb.style.background=SEASON_COLORS[t.season];
  document.getElementById('date').textContent=t.month_label||'';
  document.getElementById('uni').innerHTML=
    `<button class="${UNIT=='km'?'on':''}" onclick="setUnit('km')">km</button>`+
    `<button class="${UNIT=='mi'?'on':''}" onclick="setUnit('mi')">mi</button>`;
  const dur=fmtDur(t),d=unitDist(t.drive_km),sp=unitSpeed(t),far=unitDist(t.max_dist_from_home_km);
  document.getElementById('grid').innerHTML=
    stat('Distance',d.v,d.u)+
    stat('Avg speed',sp.v,sp.u)+
    stat('Farthest',far.v,far.u+' from home')+
    `<div class="stat gps" id="gpsTile"><div class="k">GPS points</div>
       <div class="v">${t.n_points.toLocaleString()} <span class="u">pts · hover to plot</span></div></div>`+
    `<div class="stat span2"><div class="k">Duration</div>
       <div class="v">${dur.v} <span class="u">${dur.u}</span></div></div>`;
  const gt=document.getElementById('gpsTile');
  gt.addEventListener('mouseenter',showDots);
  gt.addEventListener('mouseleave',hideDots);
  const odo=t.total_drive_legs?Math.round(100*t.odometer_legs/t.total_drive_legs):0;
  document.getElementById('qual').innerHTML=
    `<div class="row"><span class="lab">Time of year</span><b>${t.season}${t.month_label?' · '+t.month_label:''}</b></div>
     <div class="row"><span class="lab">Driving</span><b>${t.n_driving_days} day(s) · ${t.n_legs} legs · ${t.drive_hours.toFixed(1)} h</b></div>
     <div class="row"><span class="lab">Stops</span><b>${t.n_stops} (${t.n_overnight} overnight)</b></div>
     <div class="row"><span class="lab">GPS fixes</span><b>${t.n_points.toLocaleString()} pts${t.match_rate?` · road-match ${t.match_rate}`:''}</b></div>
     <div class="row"><span class="lab">Odometer legs</span><b>${t.odometer_legs}/${t.total_drive_legs} (${odo}%)</b></div>
     <div class="qbar"><i style="width:${odo}%"></i></div>`;
}
function openDetail(i){
  document.getElementById('detailview').classList.add('open');
  if(!map)initDetail();
  draw(TRIPS[i]);
  setTimeout(()=>{
    map.invalidateSize();preview.invalidateSize();
    if(curBounds&&curBounds.isValid()){
      map.fitBounds(curBounds,{padding:[60,60]});
      preview.fitBounds(curBounds,{padding:[16,16]});
    }
    animatePaths();
  },60);
}
function showList(){document.getElementById('detailview').classList.remove('open');}
document.getElementById('back').onclick=showList;
document.addEventListener('keydown',e=>{if(e.key==='Escape')showList();});
MapSettings.mountPanel();   // gear always available (list + detail)

// expose handlers used by inline attributes
window.setUnit = setUnit;
