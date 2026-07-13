import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './density.css';
import { MapSettings } from './mapsettings.js';
import TRIPS from '@alltrips';

const CAT_COLOR={"long-haul":"#1a73ff","regional":"#12a150","local":"#f59e0b"};
const DENSITY_COLOR="#1a4fd6";

const map=L.map('map',{zoomControl:false,preferCanvas:true,attributionControl:true}).setView([43,-77],6);
L.control.zoom({position:'topright'}).addTo(map);
MapSettings.manage(map,{maxZoom:19});   // basemap governed by shared Map settings
const renderer=L.canvas({padding:0.4});

let MODE='density', OPACITY=0.08;
let DENSITY_HUE="#1a4fd6";
const layers=[];   // {poly, category}
TRIPS.forEach(t=>t.lines.forEach(line=>{
  if(line.length<2)return;
  const poly=L.polyline(line,{renderer,color:DENSITY_COLOR,weight:2,opacity:OPACITY,
    smoothFactor:2,lineJoin:'round',lineCap:'round',interactive:false}).addTo(map);
  layers.push({poly,category:t.category});
}));

document.getElementById('ntrips').textContent=TRIPS.length.toLocaleString();
document.getElementById('npts').textContent=
  TRIPS.reduce((s,t)=>s+t.lines.reduce((a,l)=>a+l.length,0),0).toLocaleString();

function restyle(){
  layers.forEach(({poly,category})=>poly.setStyle({
    color:MODE==='cat'?CAT_COLOR[category]:DENSITY_HUE, opacity:OPACITY}));
}
function setOpacity(v){OPACITY=v;restyle();}
function setMode(m){
  MODE=m;
  document.getElementById('mDensity').classList.toggle('on',m==='density');
  document.getElementById('mCat').classList.toggle('on',m==='cat');
  legend();restyle();
}
function legend(){
  const el=document.getElementById('legend');
  if(MODE==='density'){
    el.innerHTML=`<div class="lab">Travel density</div>
      <div class="ramp"></div>
      <div class="ends"><span>one trip</span><span>many trips</span></div>`;
  }else{
    el.innerHTML=`<div class="lab">Category</div>
      <div class="chips">
        <div class="chip"><i style="background:#1a73ff"></i>Long-haul · ≥300 km</div>
        <div class="chip"><i style="background:#12a150"></i>Regional · 75–300 km</div>
        <div class="chip"><i style="background:#f59e0b"></i>Local · &lt;75 km</div>
      </div>`;
  }
}
legend();

// initial fit: North American cluster (most trips), overseas trips still render
const b=L.latLngBounds([]);
TRIPS.forEach(t=>t.lines.forEach(l=>l.forEach(p=>{
  if(p[1]<-50&&p[1]>-135&&p[0]>20&&p[0]<60)b.extend(p);})));
if(b.isValid())map.fitBounds(b,{padding:[30,30]});

// shared map-settings panel; on dark basemaps use a bright hue so density
// accumulates as glow rather than washing out
MapSettings.mountPanel();
MapSettings.subscribe(function(s){
  DENSITY_HUE = s.base==='dark' ? '#61b4ff' : '#1a4fd6';
  restyle();
});

// expose handlers used by inline attributes
window.setMode = setMode;
window.setOpacity = setOpacity;
