import L from 'leaflet';
import './mapsettings.css';

(function(){
  var KEY='rt_mapsettings';
  var DEFAULTS={base:'light',labels:true,opacity:1};
  function load(){try{return Object.assign({},DEFAULTS,JSON.parse(localStorage.getItem(KEY)||'{}'));}
    catch(e){return Object.assign({},DEFAULTS);}}
  function save(s){try{localStorage.setItem(KEY,JSON.stringify(s));}catch(e){}}
  function url(base,labels){
    if(base==='voyager')return labels
      ?'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'
      :'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_nolabels/{z}/{x}/{y}.png';
    if(base==='dark')return labels
      ?'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
      :'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png';
    return labels
      ?'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'
      :'https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png';
  }
  var settings=load(), managed=[], subs=[];
  function applyTo(e){
    var labels=(e.opts.forceLabels!==undefined)?e.opts.forceLabels:settings.labels;
    var base=e.opts.forceBase||settings.base;
    if(e.layer)e.map.removeLayer(e.layer);
    e.layer=L.tileLayer(url(base,labels),{subdomains:'abcd',maxZoom:e.opts.maxZoom||19,
      attribution:'© OpenStreetMap © CARTO',
      opacity:(e.opts.opacity!==undefined?e.opts.opacity:settings.opacity)});
    e.layer.addTo(e.map);
  }
  function applyAll(){managed.forEach(applyTo);subs.forEach(function(f){try{f(settings);}catch(e){}});}
  function sync(){
    var base=document.getElementById('ms-base');if(!base)return;
    base.querySelectorAll('button').forEach(function(b){
      b.classList.toggle('on',b.getAttribute('data-b')===settings.base);});
    document.getElementById('ms-labels').checked=!!settings.labels;
    document.getElementById('ms-op').value=Math.round(settings.opacity*100);
  }
  var MS={
    manage:function(map,opts){var e={map:map,opts:opts||{},layer:null};managed.push(e);applyTo(e);return e;},
    get:function(){return settings;},
    set:function(patch){settings=Object.assign({},settings,patch);save(settings);applyAll();sync();},
    subscribe:function(f){subs.push(f);try{f(settings);}catch(e){}},
    isDark:function(){return settings.base==='dark';},
    showGear:function(v){var g=document.getElementById('ms-gear');if(g)g.style.display=v?'block':'none';
      if(!v){var p=document.getElementById('ms-panel');if(p)p.classList.remove('open');}},
    mountPanel:function(){
      if(document.getElementById('ms-gear'))return;
      var gear=document.createElement('div');gear.id='ms-gear';gear.innerHTML='⚙';gear.title='Map settings';
      var p=document.createElement('div');p.id='ms-panel';
      p.innerHTML='<div class="ms-h">Map settings</div>'
        +'<div class="ms-row"><span>Basemap</span><div class="ms-seg" id="ms-base">'
        +'<button data-b="light">Light</button><button data-b="voyager">Voyager</button>'
        +'<button data-b="dark">Dark</button></div></div>'
        +'<div class="ms-row"><span>Place names</span>'
        +'<label class="ms-sw"><input type="checkbox" id="ms-labels"><span></span></label></div>'
        +'<div class="ms-row"><span>Map opacity</span><input type="range" id="ms-op" min="20" max="100"></div>';
      document.body.appendChild(gear);document.body.appendChild(p);
      gear.onclick=function(){p.classList.toggle('open');};
      p.querySelectorAll('#ms-base button').forEach(function(b){
        b.onclick=function(){MS.set({base:b.getAttribute('data-b')});};});
      document.getElementById('ms-labels').onchange=function(e){MS.set({labels:e.target.checked});};
      document.getElementById('ms-op').oninput=function(e){MS.set({opacity:e.target.value/100});};
      sync();
    }
  };
  window.MapSettings=MS;
})();

export const MapSettings = window.MapSettings;
