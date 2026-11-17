"""Carte des départements en attente des données de risque."""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

LEAFLET_VENDOR_PATH = Path(__file__).resolve().parent / "timeline_component" / "vendor"
DEPARTMENTS_URL = (
    "https://raw.githubusercontent.com/gregoiredavid/france-geojson/"
    "master/departements.geojson"
)


def build_risk_map_html() -> str:
    leaflet_css = (LEAFLET_VENDOR_PATH / "leaflet.css").read_text(encoding="utf-8")
    leaflet_js = (LEAFLET_VENDOR_PATH / "leaflet.js").read_text(encoding="utf-8")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{leaflet_css}</style>"
        "<style>"
        "html,body,#layout{height:100%;margin:0}"
        "body{font:13px system-ui,sans-serif;color:#1f2933}"
        "#layout{display:flex;background:#fff}"
        "#map{height:100%;flex:1;min-width:0}"
        "#details{box-sizing:border-box;width:280px;padding:18px;border-left:1px solid #cfd8e0;overflow:auto}"
        "#details h2{margin:0 0 12px;color:#1b3c59;font-size:18px}"
        "#status{color:#5a6875;line-height:1.5}"
        ".detail-card{margin-top:14px;padding:12px;background:#eef2f6;border:1px solid #cfd8e0}"
        ".detail-card p{margin:8px 0 0}"
        ".detail-label{color:#5a6875;font-size:12px}"
        ".detail-value{font-weight:600;color:#1b3c59}"
        ".source{margin-top:18px;color:#5a6875;font-size:11px}"
        "@media(max-width:700px){#layout{flex-direction:column}#map{height:65%;flex:none}#details{width:100%;flex:1;border-left:0;border-top:1px solid #cfd8e0}}"
        "</style>"
        f"<script>{leaflet_js}</script>"
        "</head><body><main id='layout'>"
        "<div id='map' aria-label='Carte des départements français'></div>"
        "<aside id='details' aria-live='polite'>"
        "<h2>Carte des risques</h2>"
        "<p id='status'>Chargement des départements…</p>"
        "<div id='selected-department'></div>"
        "<p class='source'>Contours : IGN Admin Express COG via france-geojson · Fond : OpenStreetMap</p>"
        "</aside></main><script>"
        "const map=L.map('map',{scrollWheelZoom:true}).setView([46.5,2.3],6);"
        "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',"
        "{attribution:'&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a>',maxZoom:19}).addTo(map);"
        "const status=document.getElementById('status');"
        "const details=document.getElementById('selected-department');"
        "let departmentLayer=null;let selectedLayer=null;"
        "const defaultStyle={color:'#42627e',weight:1,fillColor:'#7da9c9',fillOpacity:0.14};"
        "const selectedStyle={color:'#b71c2c',weight:2,fillColor:'#e54b55',fillOpacity:0.48};"
        "function addDetail(container,label,value){"
        "const item=document.createElement('p');"
        "const title=document.createElement('span');title.className='detail-label';title.textContent=label+': ';"
        "const content=document.createElement('span');content.className='detail-value';content.textContent=value;"
        "item.append(title,content);container.append(item);}"
        f"fetch('{DEPARTMENTS_URL}').then(response=>{{"
        "if(!response.ok)throw new Error('HTTP '+response.status);return response.json();"
        "}).then(data=>{"
        "const features=data.features.filter(feature=>{"
        "const code=String((feature.properties||{}).code||'');return !code.startsWith('97')&&!code.startsWith('98');"
        "});"
        "departmentLayer=L.geoJSON(features,{style:()=>defaultStyle,onEachFeature:(feature,layer)=>{"
        "layer.on({"
        "mouseover:()=>{if(layer!==selectedLayer)layer.setStyle({weight:2,fillOpacity:0.38});},"
        "mouseout:()=>{if(layer!==selectedLayer)departmentLayer.resetStyle(layer);},"
        "click:()=>{"
        "if(selectedLayer)departmentLayer.resetStyle(selectedLayer);selectedLayer=layer;layer.setStyle(selectedStyle);"
        "const properties=feature.properties||{};"
        "const name=String(properties.nom||'Département');const code=String(properties.code||'');"
        "details.replaceChildren();const heading=document.createElement('h2');"
        "heading.textContent=name;details.append(heading);"
        "const card=document.createElement('div');card.className='detail-card';"
        "addDetail(card,'Code département',code);"
        "addDetail(card,'Niveau de risque','Données à venir');"
        "addDetail(card,'Incendies recensés','Données à connecter');"
        "details.append(card);status.textContent='Informations provisoires';"
        "}"
        "});"
        "}}).addTo(map);status.textContent='Cliquez sur un département pour afficher ses informations.';"
        "}).catch(error=>{status.textContent='Impossible de charger les départements : '+error.message;});"
        "requestAnimationFrame(()=>map.invalidateSize());"
        "</script></body></html>"
    )


def render_risk_map() -> None:
    try:
        map_html = build_risk_map_html()
    except OSError as error:
        st.error(f"Impossible de charger les fichiers cartographiques : {error}")
        return
    components.html(map_html, height=640, scrolling=False)
