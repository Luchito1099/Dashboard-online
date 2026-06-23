// core/static/core/js/rotulador/app.jsx
// Rotulador embebido en el dashboard. Adaptado de index_rotulado.html:
//  - SIN seguimiento/CRM, SIN Supabase/DB/Webhook, SIN SUNAT.
//  - Datos persistidos en el backend Django (rótulos, config) vía API.
//  - IA por proxy en el servidor (no expone la API key en el navegador).
const {useState,useEffect,useRef,useMemo}=React;

const PER_PAGE=6;
const PALETTE=["#c0532a","#1a1815","#2f6b3b","#1f5a8a","#6a3b7a","#b8862b","#4a5560","#a93b6e"];

const AGENCIES=["Chachapoyas Co Dos De Mayo","Chachapoyas Jr Grau","Bagua Capital","Pedro Ruiz","Luya","Bagua Grande","Huaraz","Carhuaz","Casma","Huarmey","Caraz","Av Enrique Meiggs","Av Jose Galvez","Santa","Ovalo De La Familia","Tres De Octubre","Garatea","Yungay","Abancay","Andahuaylas","Av Parra 379 Co","Mall Lambramani","Av Lima","Plaza La Tomilla","Av Charcani","Ciudad Municipal","Av Pumacahua","Zamacola","Av Los Incas","Autopista La Joya","Jacobo Hunter","El Cruce La Joya","Mariano Melgar","Miraflores Arequipa","Urb Manuel Prado","Av Jesus","Uchumayo","Yura","Camana","Chala","Aplao","Mollendo Co","Cercado Mollendo","Cocachacra","Matarani","Ayacucho Co","Carmen Alto","San Juan Bautista","Jesus Nazareno","Huanta","Cajamarca Co","Barrio San Jose","Huambocancha Baja","Baños Del Inca","Cajabamba","Celendin","Chota","Cutervo","Bambamarca","Jaen","San Ignacio","San Marcos","Callao Faucett","Av Quilca","Av Bertello Callao","Av Saenz Peña","Bellavista Callao","Ovalo La Perla","Mi Peru","Tica Tica","San Jeronimo","Cachimayo - San Sebastian","Via Expresa Sur","Cusco Co Via Evitamiento","Av Antonio Lorena","Huancaro","Cusco Parque Industrial","Av Pachacutec","Velasco Astete","Anta Izcuchaca","Cusco Calca","Pisac","Sicuani Co Ovalo San Andres","Sicuani Av Manuel Callo","Combapata","Santo Tomas","Espinar","Quillabamba","Urcos","Ocongate","Oropesa","Cusco Urubamba","Chinchero","Huancavelica","Amarilis Co","Ambo","Tingo Maria Co Buenos Aires","Tingo María - Leoncio Prado","Aucayacu","Ica San Joaquin","La Tinguiña","Parcona","Salas Ica","Ica Santiago","Prolong Luis Massaro","Calle Los Angeles","Chincha Pueblo Nuevo","Sunampe Co","San Juan De Marcona","La Villa Cruce Pisco","San Clemente","Huancayo Jr. Ica","Terminal Los Andes","San Carlos Huancayo","Chilca Huancayo","Ciudad Universitaria","Pilcomayo","San Agustin De Cajas","Concepcion","La Merced","Perene","Pichanaki","San Ramón","Jauja","Satipo","Mazamari","Pangoa","Tarma","La Oroya","Chupaca","Calle Liverpool","Trujillo La Perla","Atahualpa","Calle Santa Cruz - America Sur","Av Hnos Uceda - America Norte","Ovalo Papal","Av Hermanos Angulo","Alto Trujillo","Ovalo Huanchaco Co","El Milagro","Av Tahuantinsuyo","Wichanzao","Moche","Paijan","Casa Grande","Chepen","Pacanguilla","Otuzco","San Pedro De Lloc","Ciudad De Dios","Guadalupe La Libertad","Pacasmayo Las Palmeras","Pacasmayo Centro","Huamachuco","Puente Viru","Viru Centro","Chao","Miraflores Chiclayo","Mariscal Nieto","Av Las Americas","Chongoyape","Calle Tahuantinsuyo","Monsefu","Pimentel","Reque","Patapo","Pomalca","Tuman","Ferreñafe","Lambayeque Panamericana","Lambayeque Centro","Jayanca","Morrope","Motupe","Olmos","Tucume","Lima Av Tingo María","Ancon","Huaycan Entrada","Puente Santa Anita","Los Sauces","Santa Clara","Av Esperanza","Av El Sol","Av Venezuela","Jr. Huaraz - Breña","Carabayllo Establo","Tungasuca","Av Tupac Amaru Km. 19","Av. Tupac Amaru Km. 23.5","Santo Domingo","El Progreso Km 22","Chorrillos Co","Chorrillos Los Faisanes","Las Delicias De Villa","Megaplaza Chorrillos","Av. Trapiche","Año Nuevo","Av Tupac Amaru Cdra. 57","Puente Nuevo","Jiron Ancash","La Cincuenta","Plaza Norte Entregas","Megaplaza Independencia","Jesus Maria","Real Plaza Salaverry","Av La Fontana","Los Fresnos","Parque La Molina","Av Mexico Co","Av. Canada","Av. Las Palmeras","Pro","Av. Angelica Gamarra","Av Huandoy Con Marañon","Chosica","Huachipa Co","Santa María De Huachipa","Nuevo Lurin","Puente Lurin","Magdalena Del Mar","Av. La Marina","Av Bolivar","Larcomar","La Curva De Manchay","Manchay Tres Marias","Puente Arica","Zapallal","Ovalo Puente Piedra","Av Buenos Aires","Punta Hermosa","Rimac Av. Amancaes","Aviacion 2819","Av. Angamos","Av. 13 De Enero","Cruz De Motupe","Sjl- Las Flores","Sjl-Av.Proceres","Canto Grande","Los Pinos","Bayovar","Campoy","Jr Chinchaysuyo Cdra 4","Av Malecon Checa Cdra. 1","Av Circunvalacion Sjl","Atocongo","Maria Auxiliadora","Av. Canevaro","Av Miguel Grau Pamplona Alta","Av San Juan Pamplona Alta","Fiori","Av Bertello Smp","Smp-Av. Proceres","Av. Peru 15","Av. Lima Cdra 38","Av. Gerardo Unger Cdra 64","Av Jose Granda Cdra 38","Av Jose Granda Cdra. 25","Av. Universitaria Cdra. 16","Av. Huarochirí","Av Santa Rosa - Sta Anita","Jr Cesar Vallejo","Santa Rosa","Higuereta","Surco Mateo Pumacahua","Rep. De Panama","Av. Principal","Av. Cesar Vallejo","Av. Pastor Sevilla","Óvalo Mariátegui","01 De Mayo","Las Conchitas","Pesquero","Av. Lima - Vmt","Av. Villa Maria","Nueva Esperanza Vmt","Barranca","Paramonga","Supe","Cañete San Vicente","Cañete Imperial","Mala","Nuevo Imperial Co","Huaral","Chancay","Jicamarca","Salaverry Huacho Co","Huacho Av Indacochea","Huaura","Sayan","Iquitos Jr Francisco Bolognesi","Iquitos Av Tupac Amaru","Punchana","Av Jose A. Quiñones","Ctra Iquitos Nauta","Yurimaguas","Tambopata Av La Joya Co","Av 15 De Agosto","Tambopata Av Circunvalacion","Mazuko","El Triunfo","Iberia","San Antonio","Calle Lima","Chen Chen","Ilo Co Pampa Inalambrica","Ilo Puerto","Ilo Pacocha","Cerro De Pasco","Huayllay","Oxapampa","Villa Rica","Av. Grau","Av Raul Mata La Cruz- Dos Grifos","Av Tacna","Tacala","Catacaos","La Union","Las Lomas","Tambo Grande","Aahh Santa Rosa Piura","Ayabaca","Paimas","Huancabamba","Chulucanas","Morropon","Paita","Sullana Santa Rosa","Sullana Co Zona Industrial","Bellavista Sullana","Ignacio Escudero","Talara Co Asoc California","Talara Alta 9 De Octubre","Talara Baja Parque 22","El Alto","Los Organos","Máncora","Sechura","Av Costanera","Salcedo","Alto Puno","Av 4 De Noviembre Co","Azangaro","Desaguadero","Ilave","Ayaviri","Jr. Mama Ocllo","Las Mercedes","Av. Lampa","Av. Modesto Borda","Av Independencia","Jr Agustin Gamarra","Av Heroes Del Pacifico Co","Ovalo Orquideas Co","Moyobamba Centro","Soritor","San Martin Bellavista","San Jose De Sisa","Saposoa","Lamas","Juanjui Centro","Picota","Rioja","Segunda Jerusalen","Nueva Cajamarca","Pardo Miguel Naranjos","Tarapoto Co Jr Alfonso Ugarte","Jr Leoncio Prado","Jr. Tahuantinsuyo","Jr. Ramón Castilla","Tarapoto La Banda De Shilcayo","Tarapoto Jr. Sargento Lorez","Av Fernando Belaunde","Jr Fredy Aliaga Co","Uchiza","Tacna Co Av. Jorge Basadre","Av Vigil","Av. Arias Araguez","Av Ejercito","Pocollay","Tacna Ciudad Nueva","Villa San Francisco","Av. Municipal","Viñanis","Tumbes - Av Arica","Tumbes Puyango","Pampa Grande Tumbes","Corrales","La Cruz Tumbes","Zorritos","Zarumilla","Aguas Verdes","Calleria Jr Jose Galvez","Calleria Av Saenz Peña","Pucallpa Co Federico Basadre","Yarinacocha Centro","Yarinacocha Av Universitaria","Manantay Av Aguaytia","Manantay Av Tupac Amaru","Aguaytía"];

const DESTINOS_SHALOM=["01 DE MAYO","AAHH SANTA ROSA PIURA","ABANCAY","AGUAS VERDES","AGUAYTÍA","ALTO PUNO","ALTO TRUJILLO","AMARILIS CO","AMBO","ANCON","ANDAHUAYLAS","ANTA IZCUCHACA","APLAO","ATAHUALPA","ATOCONGO","AUCAYACU","AUTOPISTA LA JOYA","AV  4 DE NOVIEMBRE CO","AV  BOLIVAR","AV  ESPERANZA","AV  INDEPENDENCIA","AV  JOSE GALVEZ","AV  LA FONTANA","AV  QUILCA","AV  SAN JUAN PAMPLONA ALTA","AV  SANTA ROSA - STA ANITA","AV  TUPAC AMARU KM. 19","AV  VIGIL","AV 15 DE AGOSTO","AV ANTONIO LORENA","AV BERTELLO CALLAO","AV BERTELLO SMP","AV BUENOS AIRES","AV CHARCANI","AV CIRCUNVALACION SJL","AV COSTANERA","AV EJERCITO","AV EL SOL","AV ENRIQUE MEIGGS","AV FERNANDO BELAUNDE","AV HERMANOS ANGULO","AV HEROES DEL PACIFICO CO","AV HNOS UCEDA - AMERICA NORTE","AV HUANDOY CON MARAÑON","AV JESUS","AV JOSE A. QUIÑONES","AV JOSE GRANDA CDRA 38","AV JOSE GRANDA CDRA. 25","AV LAS AMERICAS","AV LIMA","AV LOS INCAS","AV MALECON  CHECA CDRA. 1","AV MEXICO CO","AV MIGUEL GRAU  PAMPLONA ALTA","AV PACHACUTEC","AV PARRA 379 CO","AV PUMACAHUA","AV RAUL MATA LA CRUZ- DOS GRIFOS","AV SAENZ PEÑA","AV TACNA","AV TAHUANTINSUYO","AV TUPAC AMARU CDRA. 57","AV VENEZUELA","AV. 13 DE ENERO","AV. ANGAMOS","AV. ANGELICA GAMARRA","AV. ARIAS ARAGUEZ","AV. CANADA","AV. CANEVARO","AV. CESAR VALLEJO","AV. GERARDO UNGER CDRA 64","AV. GRAU","AV. HUAROCHIRÍ","AV. LA MARINA","AV. LAMPA","AV. LAS PALMERAS","AV. LIMA - VMT","AV. LIMA CDRA 38","AV. MODESTO BORDA","AV. MUNICIPAL","AV. PASTOR SEVILLA","AV. PERU 15","AV. PRINCIPAL","AV. TRAPICHE","AV. TUPAC AMARU KM. 23.5","AV. UNIVERSITARIA CDRA. 16","AV. VILLA MARIA","AVIACION 2819","AYABACA","AYACUCHO CO","AYAVIRI","AZANGARO","AÑO NUEVO","BAGUA CAPITAL","BAGUA GRANDE","BAMBAMARCA","BARRANCA","BARRIO SAN JOSE","BAYOVAR","BAÑOS DEL INCA","BELLAVISTA CALLAO","BELLAVISTA SULLANA","CACHIMAYO - SAN SEBASTIAN","CAJABAMBA","CAJAMARCA CO","CALLAO FAUCETT","CALLE LIMA","CALLE LIVERPOOL","CALLE LOS ANGELES","CALLE SANTA CRUZ - AMERICA SUR","CALLE TAHUANTINSUYO","CALLERIA AV SAENZ PEÑA","CALLERIA JR JOSE GALVEZ","CAMANA","CAMPOY","CANTO GRANDE","CARABAYLLO ESTABLO","CARAZ","CARHUAZ","CARMEN ALTO","CASA GRANDE","CASMA","CATACAOS","CAÑETE IMPERIAL","CAÑETE SAN VICENTE","CELENDIN","CERCADO MOLLENDO","CERRO DE PASCO","CHACHAPOYAS CO DOS DE MAYO","CHACHAPOYAS JR GRAU","CHALA","CHANCAY","CHAO","CHEN CHEN","CHEPEN","CHILCA HUANCAYO","CHINCHA PUEBLO NUEVO","CHINCHERO","CHONGOYAPE","CHORRILLOS CO","CHORRILLOS LOS FAISANES","CHOSICA","CHOTA","CHULUCANAS","CHUPACA","CIUDAD DE DIOS","CIUDAD MUNICIPAL","CIUDAD UNIVERSITARIA","COCACHACRA","COMBAPATA","CONCEPCION","CORRALES","CRUZ DE MOTUPE","CTRA IQUITOS NAUTA","CUSCO CALCA","CUSCO CO VIA EVITAMIENTO","CUSCO PARQUE INDUSTRIAL","CUSCO URUBAMBA","CUTERVO","DESAGUADERO","EL ALTO","EL CRUCE LA JOYA","EL MILAGRO","EL PROGRESO KM 22","EL TRIUNFO","ESPINAR","FERREÑAFE","FIORI","GARATEA","GUADALUPE LA LIBERTAD","HIGUERETA","HUACHO AV  INDACOCHEA","HUAMACHUCO","HUAMBOCANCHÁ BAJA","HUANCABAMBA","HUANCARO","HUANCAVELICA","HUANCAYO JR. ICA","HUANTA","HUARAL","HUARAZ","HUARMEY","HUAURA","HUAYCAN ENTRADA","HUAYLLAY","IBERIA","ICA SAN JOAQUIN","ICA SANTIAGO","IGNACIO ESCUDERO","ILAVE","ILO CO PAMPA INALAMBRICA","ILO PACOCHA","ILO PUERTO","IQUITOS  AV TUPAC AMARU","IQUITOS JR FRANCISCO BOLOGNESI","JACOBO HUNTER","JAEN","JAUJA","JAYANCA","JESUS MARIA","JESUS NAZARENO","JICAMARCA","JIRON ANCASH","JR  FREDY ALIAGA CO","JR AGUSTIN GAMARRA","JR CESAR VALLEJO","JR CHINCHAYSUYO CDRA 4","JR LEONCIO PRADO","JR. HUARAZ -  BREÑA","JR. MAMA OCLLO","JR. RAMÓN CASTILLA","JR. TAHUANTINSUYO","JUANJUI  CENTRO","LA CINCUENTA","LA CRUZ  TUMBES","LA CURVA DE MANCHAY","LA MERCED","LA OROYA","LA TINGUIÑA","LA UNION","LA VILLA  CRUCE PISCO","LAMAS","LAMBAYEQUE CENTRO","LAMBAYEQUE PANAMERICANA","LARCOMAR","LAS CONCHITAS","LAS DELICIAS DE VILLA","LAS LOMAS","LAS MERCEDES","LIMA AV TINGO MARÍA","LOS FRESNOS","LOS ORGANOS","LOS PINOS","LOS SAUCES","LUYA","MAGDALENA DEL MAR","MALA","MALL LAMBRAMANI","MANANTAY  AV AGUAYTIA","MANANTAY AV TUPAC AMARU","MANCHAY TRES MARIAS","MARIA AUXILIADORA","MARIANO MELGAR","MATARANI","MAZAMARI","MAZUKO","MEGAPLAZA CHORRILLOS","MEGAPLAZA INDEPENDENCIA","MI PERU","MIRAFLORES AREQUIPA","MIRAFLORES CHICLAYO","MOCHE","MOLLENDO CO","MONSEFU","MORROPE","MOTUPE","MOYOBAMBA  CENTRO","MÁNCORA","NUEVA CAJAMARCA","NUEVA ESPERANZA VMT","NUEVO IMPERIAL CO","NUEVO LURIN","OCONGATE","OLMOS","OROPESA","OTUZCO","OVALO DE LA FAMILIA","OVALO HUANCHACO CO","OVALO LA PERLA","OVALO ORQUIDEAS CO","OVALO PAPAL","OVALO PUENTE PIEDRA","OXAPAMPA","PACANGUILLA","PACASMAYO CENTRO","PACASMAYO LAS PALMERAS","PAIJAN","PAIMAS","PAITA","PAMPA GRANDE TUMBES","PANGOA","PARAMONGA","PARCONA","PARDO MIGUEL NARANJOS","PARQUE LA MOLINA","PATAPO","PEDRO RUIZ","PERENE","PESQUERO","PICHANAKI","PICOTA","PILCOMAYO","PIMENTEL","PISAC","PLAZA LA TOMILLA","PLAZA NORTE ENTREGAS","POCOLLAY","POMALCA","PRO","PROLONG LUIS MASSARO","PUCALLPA CO FEDERICO BASADRE","PUENTE ARICA","PUENTE LURIN","PUENTE NUEVO","PUENTE SANTA ANITA","PUENTE VIRU","PUNCHANA","PUNTA HERMOSA","QUILLABAMBA","REAL PLAZA SALAVERRY","REP. DE PANAMA","REQUE","RIMAC AV. AMANCAES","RIOJA","SALAS ICA","SALAVERRY HUACHO CO","SALCEDO","SAN AGUSTIN DE CAJAS","SAN ANTONIO","SAN CARLOS HUANCAYO","SAN CLEMENTE","SAN IGNACIO","SAN JERONIMO","SAN JOSE DE SISA","SAN JUAN BAUTISTA","SAN JUAN DE MARCONA","SAN MARCOS","SAN MARTIN BELLAVISTA","SAN PEDRO DE LLOC","SAN RAMÓN","SANTA","SANTA CLARA","SANTA MARÍA DE HUACHIPA","SANTA ROSA","SANTO DOMINGO","SANTO TOMAS","SAPOSOA","SATIPO","SAYAN","SECHURA","SEGUNDA JERUSALEN","SICUANI AV MANUEL CALLO","SICUANI CO OVALO SAN ANDRES","SJL- LAS FLORES","SJL-AV.PROCERES","SMP-AV. PROCERES","SORITOR","SULLANA CO ZONA INDUSTRIAL","SULLANA SANTA ROSA","SUNAMPE  CO","SUPE","SURCO MATEO PUMACAHUA","TACALA","TACNA CIUDAD NUEVA","TACNA CO AV. JORGE BASADRE","TALARA  CO ASOC CALIFORNIA","TALARA ALTA 9 DE OCTUBRE","TALARA BAJA PARQUE 22","TAMBO GRANDE","TAMBOPATA AV CIRCUNVALACION","TAMBOPATA AV LA JOYA CO","TARAPOTO CO JR ALFONSO UGARTE","TARAPOTO JR. SARGENTO LOREZ","TARAPOTO LA BANDA DE SHILCAYO","TARMA","TERMINAL LOS ANDES","TICA TICA","TINGO MARIA CO BUENOS AIRES","TINGO MARÍA - LEONCIO PRADO","TRES DE OCTUBRE","TRUJILLO LA PERLA","TUCUME","TUMAN","TUMBES - AV ARICA","TUMBES PUYANGO","TUNGASUCA","UCHIZA","UCHUMAYO","URB MANUEL PRADO","URCOS","VELASCO ASTETE","VIA EXPRESA SUR","VILLA RICA","VILLA SAN FRANCISCO","VIRU CENTRO","VIÑANIS","WICHANZAO","YARINACOC  AV UNIVERSITARIA","YARINACOC CENTRO","YUNGAY","YURA","YURIMAGUAS","ZAMACOLA","ZAPALAL","ZARUMILLA","ZORRITOS","ÓVALO MARIÁTEGUI"];

// ── Shalom ──
const normShalom=t=>String(t).toUpperCase().normalize("NFD").replace(/\p{Mn}/gu,"");
function buscarDestinoShalom(raw){
  if(!raw)return"";
  const n=normShalom(raw);
  const normed=DESTINOS_SHALOM.map(d=>normShalom(d));
  const exact=normed.indexOf(n);
  if(exact!==-1)return DESTINOS_SHALOM[exact];
  const contains=normed.findIndex(d=>d===n||d.includes(n)||n.includes(d));
  if(contains!==-1)return DESTINOS_SHALOM[contains];
  const words=n.split(/\s+/).filter(w=>w.length>2);
  let bestScore=0,bestIdx=-1;
  normed.forEach((d,i)=>{const s=words.filter(w=>d.includes(w)).length;if(s>bestScore){bestScore=s;bestIdx=i;}});
  if(bestIdx!==-1&&bestScore>0)return DESTINOS_SHALOM[bestIdx];
  return raw.toUpperCase();
}
function detectarMercaderia(nombre,products){
  const n=normShalom(nombre||"");
  if(products&&products.length){const m=products.find(p=>normShalom(p.nombre)===n);if(m)return m.mercaderia;}
  if(["RODILL","MUNEQUERA","TOBILLER","SOPORTE"].some(k=>n.includes(k)))return"PAQUETE XS";
  if(["REFLECTIV","TELA"].some(k=>n.includes(k)))return"PAQUETE S";
  return"PAQUETE XS";
}
function exportarFormatoShalom(orders,products){
  if(!orders||orders.length===0){alert("No hay pedidos para exportar.");return;}
  const headers=["DESTINATARIO (DOC)","TELF. DESTINATARIO","CONTACTO (DOC)","TELF. CONTACTO","NRO GRR","ORIGEN","DESTINO","MERCADERIA","ALTO","ANCHO","LARGO","PESO","CANTIDAD"];
  const filas=orders.map(o=>{
    let tel=String(o.celular||"").replace(/\D/g,"");
    if(tel.startsWith("51")&&tel.length===11)tel=tel.slice(2);
    tel=tel.slice(-9);
    return[o.dni||"",tel,"","","","PUNTA HERMOSA",buscarDestinoShalom(o.agencia||o.destino||""),detectarMercaderia(o.producto||"",products),0.1,0.1,0.1,1,Number(o.cantidad)||1];
  });
  const ws=XLSX.utils.aoa_to_sheet([headers,...filas]);
  ws["!cols"]=[20,18,15,15,10,18,25,12,8,8,8,8,10].map(w=>({wch:w}));
  const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,"Hoja1");XLSX.writeFile(wb,"formato_shalom.xlsx");
}

// ── Impresión ──
function buildPrintHtml(orders,page,all,totalPages,cfg,logoUrl){
  const pages=all?Array.from({length:totalPages},(_,i)=>i):[page-1];
  const sheets=pages.map(pi=>{
    const cells=[0,1,2,3,4,5].map(i=>{
      const o=orders[pi*PER_PAGE+i];
      if(!o)return`<div style="padding:3mm"><div style="border:1.5px dashed #d0ccc4;min-height:88mm;border-radius:2mm"></div></div>`;
      const hBg=cfg.labelStyle==="bold"?cfg.accent:(cfg.headerBg||"#fdfcfa");
      const hCol=cfg.labelStyle==="bold"?"#fff":"#1c1a17";
      const bdr=cfg.labelStyle==="bold"?`2px solid ${cfg.accent}`:cfg.labelStyle==="minimal"?"1px solid #d0ccc4":"1.5px solid #1c1a17";
      const barH=cfg.labelStyle==="minimal"?0:cfg.accentBarHeight;
      const logo=logoUrl?`<img src="${logoUrl}" style="height:6mm;max-width:20mm;object-fit:contain">`:`<div style="width:5mm;height:5mm;border-radius:1mm;background:${cfg.labelStyle==="bold"?"#fff":cfg.accent};display:inline-flex;align-items:center;justify-content:center;color:${cfg.labelStyle==="bold"?cfg.accent:"#fff"};font-weight:700;font-size:7pt">${cfg.initial||"•"}</div>`;
      return`<div style="padding:3mm"><div style="border:${bdr};border-radius:2mm;background:${cfg.bodyBg||"#fff"};overflow:hidden;font-family:Arial,sans-serif;color:#1c1a17">
        <div style="height:${barH}mm;background:${cfg.accent}"></div>
        <div style="display:flex;align-items:center;justify-content:space-between;padding:2mm 3mm;border-bottom:1px solid ${cfg.labelStyle==="bold"?"transparent":"#1c1a17"};background:${hBg}">
          <div style="display:flex;align-items:center;gap:2mm">${logo}<span style="font-weight:700;font-size:8pt;text-transform:uppercase;color:${hCol}">${cfg.brand}</span></div>
          <span style="font-size:6pt;color:#888;font-family:monospace">RT-${String(10245+((o.id||0)%1000)).padStart(5,"0")}</span>
        </div>
        <div style="padding:2.5mm 3mm 2mm;border-bottom:1px dashed #ccc">
          <div style="font-size:5.5pt;text-transform:uppercase;color:#999;margin-bottom:1mm;font-family:monospace;font-weight:600">Destinatario</div>
          <div style="font-size:${cfg.nameFontSize}pt;font-weight:700;line-height:1.2">${o.nombres||"—"}</div>
        </div>
        <div style="padding:2mm 3mm;border-bottom:1px dashed #ccc">
          <div style="font-size:5.5pt;text-transform:uppercase;color:#999;margin-bottom:1mm;font-family:monospace;font-weight:600">Dirección de entrega</div>
          <div style="font-size:9pt;font-weight:500;line-height:1.3;color:#2a2825">${o.destino||"—"}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;border-bottom:1px dashed #ccc">
          <div style="padding:2mm 3mm;border-right:1px dashed #ccc"><div style="font-size:5.5pt;text-transform:uppercase;color:#999;margin-bottom:1mm;font-family:monospace;font-weight:600">Agencia Shalom</div><div style="font-size:7.5pt;font-weight:500;color:#4a4845">${o.agencia||"—"}</div></div>
          <div style="padding:2mm 3mm"><div style="font-size:5.5pt;text-transform:uppercase;color:#999;margin-bottom:1mm;font-family:monospace;font-weight:600">Celular</div><div style="font-size:8pt;font-weight:700;font-family:monospace">${o.celular||"—"}</div></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr">
          <div style="padding:2mm 3mm;border-right:1px dashed #ccc"><div style="font-size:5.5pt;text-transform:uppercase;color:#999;margin-bottom:1mm;font-family:monospace;font-weight:600">Producto</div><div style="font-size:7.5pt;font-weight:500;color:#4a4845">${o.producto||"—"}</div></div>
          <div style="padding:2mm 3mm"><div style="font-size:5.5pt;text-transform:uppercase;color:#999;margin-bottom:1mm;font-family:monospace;font-weight:600">DNI</div><div style="font-size:8pt;font-weight:700;font-family:monospace">${o.dni||"—"}</div></div>
        </div>
        <div style="padding:1.5mm 3mm;border-top:1.5px solid ${cfg.labelStyle==="minimal"?"#d0ccc4":"#1c1a17"};display:flex;align-items:center;justify-content:space-between;font-size:5.5pt;font-family:monospace;background:${cfg.labelStyle==="bold"?cfg.accent:(cfg.footerBg||"#fdfcfa")}">
          ${cfg.showFragile?`<span style="text-transform:uppercase;color:${cfg.labelStyle==="bold"?"#fff":"#999"}">Frágil · No doblar</span>`:"<span></span>"}
          ${cfg.showBarcode?`<div style="height:4mm;width:18mm;background:repeating-linear-gradient(90deg,#1c1a17 0 1px,transparent 1px 3px,#1c1a17 3px 5px,transparent 5px 6px)"></div>`:""}
          ${cfg.showCounter?`<span style="font-weight:600;color:${cfg.labelStyle==="bold"?"#fff":"#555"}">#${String(i+1).padStart(2,"0")}/06</span>`:"<span></span>"}
        </div>
      </div></div>`;
    }).join("");
    return`<div style="width:210mm;height:297mm;background:#fff;display:grid;grid-template-columns:1fr 1fr;padding:6mm;box-sizing:border-box;page-break-after:always">${cells}</div>`;
  }).join("");
  return`<!DOCTYPE html><html><head><meta charset="utf-8"><title>Rótulos ${cfg.brand}</title><style>*{box-sizing:border-box;margin:0;padding:0}body{background:#fff}@page{size:210mm 297mm;margin:0}@media print{*{-webkit-print-color-adjust:exact!important;print-color-adjust:exact!important}}</style></head><body>${sheets}</body></html>`;
}
function doPrint(orders,page,all,totalPages,cfg,logoUrl){
  const html=buildPrintHtml(orders,page,all,totalPages,cfg,logoUrl);
  const w=window.open("","_blank");
  if(!w){alert("Activa popups para este sitio e intenta de nuevo.");return;}
  w.document.write(html);w.document.close();w.focus();setTimeout(()=>w.print(),500);
}

// ── API (backend Django) ──
const CSRF=(document.querySelector("input[name=csrfmiddlewaretoken]")||{}).value||"";
async function api(url,opts={}){
  const r=await fetch(url,{headers:{"Content-Type":"application/json","X-CSRFToken":CSRF},...opts});
  if(!r.ok){let m;try{m=(await r.json()).error;}catch{}throw new Error(m||("HTTP "+r.status));}
  return r.json();
}
const API={
  config:()=>api("/rotulador/api/config/"),
  saveConfig:d=>api("/rotulador/api/config/",{method:"POST",body:JSON.stringify(d)}),
  rotulos:()=>api("/rotulador/api/rotulos/"),
  crear:d=>api("/rotulador/api/rotulos/",{method:"POST",body:JSON.stringify(d)}),
  editar:(id,d)=>api("/rotulador/api/rotulos/"+id+"/",{method:"PUT",body:JSON.stringify(d)}),
  borrar:id=>api("/rotulador/api/rotulos/"+id+"/",{method:"DELETE"}),
  pedidos:()=>api("/rotulador/api/pedidos/"),
  extraer:d=>api("/rotulador/api/extraer/",{method:"POST",body:JSON.stringify(d)}),
};

const pJSON=t=>{try{const m=t.match(/\{[\s\S]*\}/);return m?JSON.parse(m[0]):null;}catch{return null;}};
const f2b64=f=>new Promise((r,j)=>{const x=new FileReader();x.onload=()=>r(x.result.split(",")[1]);x.onerror=j;x.readAsDataURL(f);});
const f2url=f=>new Promise((r,j)=>{const x=new FileReader();x.onload=()=>r(x.result);x.onerror=j;x.readAsDataURL(f);});
const Spin=()=><span style={{display:"inline-block",animation:"rot-spin .7s linear infinite",marginRight:5}}>⟳</span>;

// Autocompletar agencia
function AcInput({value,onChange,placeholder,suggestions=AGENCIES}){
  const[open,setOpen]=useState(false);const[filt,setFilt]=useState([]);const wr=useRef(null);
  const build=v=>{const q=(v||"").toLowerCase();return suggestions.filter(s=>s.toLowerCase().includes(q)).slice(0,40);};
  const handle=v=>{onChange(v);setFilt(build(v));setOpen(true);};
  useEffect(()=>{const fn=e=>{if(wr.current&&!wr.current.contains(e.target))setOpen(false);};document.addEventListener("mousedown",fn);return()=>document.removeEventListener("mousedown",fn);},[]);
  return(<div ref={wr} style={{position:"relative"}}>
    <input value={value} onChange={e=>handle(e.target.value)} onFocus={()=>{setFilt(build(value));setOpen(true);}} placeholder={placeholder} style={I}/>
    {open&&filt.length>0&&<div style={{position:"absolute",top:"calc(100% + 4px)",left:0,right:0,background:"#fff",border:"1.5px solid #d0c8bc",borderRadius:8,maxHeight:200,overflowY:"auto",zIndex:50,boxShadow:"0 6px 20px #0002"}}>
      {filt.map(s=><div key={s} onClick={()=>{onChange(s);setOpen(false);}} style={{padding:"8px 11px",fontSize:13,cursor:"pointer",borderBottom:"1px solid #f0ece5"}} onMouseEnter={e=>e.currentTarget.style.background="#faf6ef"} onMouseLeave={e=>e.currentTarget.style.background="#fff"}>{s}</div>)}
    </div>}
  </div>);
}

const I={width:"100%",padding:"9px 11px",border:"1.5px solid #ccc",borderRadius:8,fontSize:14,background:"#fff",color:"#1a1a1a",boxSizing:"border-box"};
const LBL=t=><div style={{fontSize:11,fontWeight:700,textTransform:"uppercase",letterSpacing:".09em",color:"#7a6a5a",marginBottom:4}}>{t}</div>;

// Formulario de campos (reutilizado por crear/editar)
function CamposPedido({f,set,products}){
  return(<>
    <div>{LBL("Destinatario *")}<input value={f.nombres||""} onChange={e=>set("nombres",e.target.value)} placeholder="Nombre completo" style={I}/></div>
    <div>{LBL("Dirección *")}<input value={f.destino||""} onChange={e=>set("destino",e.target.value)} placeholder="Av. Los Olivos 482, Trujillo" style={I}/></div>
    <div>{LBL("Agencia Shalom")}<AcInput value={f.agencia||""} onChange={v=>set("agencia",v)} placeholder="Buscar…"/></div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:9}}>
      <div>{LBL("Celular")}<input value={f.celular||""} onChange={e=>set("celular",e.target.value)} placeholder="987 654 321" style={I}/></div>
      <div>{LBL("DNI")}<input value={f.dni||""} onChange={e=>set("dni",e.target.value)} placeholder="70123456" style={I}/></div>
    </div>
    <div>{LBL("Producto")}<AcInput value={f.producto||""} onChange={v=>set("producto",v)} placeholder="TOBILLERA NOVAFIT…" suggestions={(products||[]).map(p=>p.nombre)}/></div>
    <div style={{width:120}}>{LBL("Cantidad")}<input type="number" min={1} max={99} value={f.cantidad||1} onChange={e=>set("cantidad",Math.max(1,parseInt(e.target.value)||1))} style={{...I,fontWeight:700,textAlign:"center"}}/></div>
  </>);
}

function PreviewCard({data,onConfirm,onCancel,products}){
  const[f,setF]=useState({cantidad:1,...data});const set=(k,v)=>setF(p=>({...p,[k]:v}));
  return(<div style={{border:"2px solid #c0532a",borderRadius:10,padding:14,background:"#fff8f4",display:"flex",flexDirection:"column",gap:10}}>
    <div style={{fontSize:13,fontWeight:700,color:"#c0532a"}}>✓ Revisa y confirma</div>
    <CamposPedido f={f} set={set} products={products}/>
    <div style={{display:"flex",gap:8}}>
      <button onClick={()=>onConfirm(f)} style={{...BTN,flex:1}}>Agregar pedido</button>
      <button onClick={onCancel} style={BTN_SEC}>Cancelar</button>
    </div>
  </div>);
}

const BTN={padding:"11px",background:"#c0532a",color:"#fff",border:"none",borderRadius:8,fontSize:14,fontWeight:700,cursor:"pointer"};
const BTN_SEC={padding:"11px 14px",background:"#fff",border:"1.5px solid #ccc",borderRadius:8,fontSize:13,cursor:"pointer",color:"#666",fontWeight:600};

function FormTab({onAdd,products}){
  const E={nombres:"",destino:"",agencia:"",celular:"",dni:"",producto:"",cantidad:1};
  const[f,setF]=useState(E);const set=(k,v)=>setF(p=>({...p,[k]:v}));
  const add=()=>{if(!f.nombres.trim()&&!f.destino.trim())return;onAdd({...f,origen:"manual"});setF(E);};
  return(<div style={{display:"flex",flexDirection:"column",gap:10}}><CamposPedido f={f} set={set} products={products}/><button onClick={add} style={BTN}>+ Agregar pedido</button></div>);
}

function PasteTab({onAdd,products}){
  const[text,setText]=useState("");const[loading,setLoading]=useState(false);const[err,setErr]=useState("");const[preview,setPreview]=useState(null);
  const analyze=async()=>{setErr("");setPreview(null);if(!text.trim()){setErr("Pega algún texto.");return;}setLoading(true);try{const r=await API.extraer({text});setPreview(r.data);}catch(e){setErr(e.message);}finally{setLoading(false);}};
  return(<div style={{display:"flex",flexDirection:"column",gap:10}}>
    <div style={{fontSize:13,color:"#6a5a4a",padding:"9px 11px",background:"#f5f0e8",borderRadius:8,border:"1px solid #e0d8cc"}}>📋 Pega un chat de WhatsApp o mensaje con los datos del pedido.</div>
    <textarea value={text} onChange={e=>setText(e.target.value)} placeholder={"Ej:\nCliente: Juan Pérez\nDirección: Av. Larco 1450\nCelular: 987654321\nProducto: TOBILLERA NOVAFIT\nDNI: 72345678"} style={{...I,minHeight:120,fontFamily:"monospace",resize:"vertical"}}/>
    {loading&&<div style={{padding:"10px 12px",background:"#fffbf5",borderRadius:8,fontSize:13,color:"#7a5a3a",border:"1px solid #e8d8c0"}}><Spin/>IA analizando…</div>}
    {err&&<div style={{padding:"10px 12px",borderRadius:8,fontSize:13,background:"#fef2f2",border:"1.5px solid #f5b8b8",color:"#9b2020"}}>{err}</div>}
    {!preview&&<button onClick={analyze} disabled={loading||!text.trim()} style={{...BTN,background:loading||!text.trim()?"#c8a090":"#c0532a"}}>✦ Analizar con IA</button>}
    {preview&&<PreviewCard data={preview} products={products} onConfirm={o=>{onAdd({...o,origen:"mensaje"});setPreview(null);setText("");}} onCancel={()=>setPreview(null)}/>}
  </div>);
}

function FotoTab({onAdd,products}){
  const[file,setFile]=useState(null);const[url,setUrl]=useState(null);const[loading,setLoading]=useState(false);const[err,setErr]=useState("");const[preview,setPreview]=useState(null);const fr=useRef(null);
  const hf=f=>{if(!f)return;setFile(f);setErr("");setPreview(null);setUrl(URL.createObjectURL(f));};
  const extract=async()=>{if(!file){setErr("Selecciona imagen.");return;}setLoading(true);setErr("");try{const b64=await f2b64(file);const r=await API.extraer({image_base64:b64,media_type:file.type});setPreview(r.data);}catch(e){setErr(e.message);}finally{setLoading(false);}};
  return(<div style={{display:"flex",flexDirection:"column",gap:10}}>
    <div onClick={()=>fr.current?.click()} style={{border:"2px dashed #c8b8a8",borderRadius:10,padding:20,textAlign:"center",background:"#faf7f3",cursor:"pointer"}}>
      <div style={{fontSize:28}}>📷</div><div style={{fontWeight:700,color:"#4a3a2a",fontSize:14}}>Sube una foto</div><div style={{fontSize:12,color:"#9a8070"}}>JPG, PNG, WEBP</div>
    </div>
    <input ref={fr} type="file" accept="image/*" onChange={e=>{hf(e.target.files?.[0]);e.target.value="";}} style={{display:"none"}}/>
    {url&&<img src={url} style={{width:"100%",maxHeight:160,objectFit:"cover",borderRadius:8,border:"2px solid #d0c8bc"}}/>}
    {loading&&<div style={{padding:"10px",background:"#fffbf5",borderRadius:8,fontSize:13,color:"#7a5a3a",border:"1px solid #e8d8c0"}}><Spin/>Analizando imagen…</div>}
    {err&&<div style={{padding:"10px",borderRadius:8,fontSize:13,background:"#fef2f2",border:"1.5px solid #f5b8b8",color:"#9b2020"}}>{err}</div>}
    {!preview&&<button onClick={extract} disabled={!file||loading} style={{...BTN,background:!file||loading?"#c8a090":"#c0532a"}}>✦ Extraer con IA</button>}
    {preview&&<PreviewCard data={preview} products={products} onConfirm={o=>{onAdd({...o,origen:"mensaje"});setPreview(null);setFile(null);setUrl(null);}} onCancel={()=>setPreview(null)}/>}
  </div>);
}

function ImportTab({onImport}){
  const[pedidos,setPedidos]=useState(null);const[loading,setLoading]=useState(false);const[err,setErr]=useState("");
  const cargar=async()=>{setLoading(true);setErr("");try{const r=await API.pedidos();setPedidos(r.pedidos);}catch(e){setErr(e.message);}finally{setLoading(false);}};
  useEffect(()=>{cargar();},[]);
  const importar=p=>{onImport({nombres:p.nombres,destino:p.destino,celular:p.celular,dni:p.dni,producto:p.producto,cantidad:p.cantidad,agencia:buscarDestinoShalom(p.distrito||p.provincia||""),origen:"shopify",pedido_id:p.pedido_id});setPedidos(prev=>prev.filter(x=>x.pedido_id!==p.pedido_id));};
  return(<div style={{display:"flex",flexDirection:"column",gap:10}}>
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
      <div style={{fontSize:13,color:"#6a5a4a"}}>Pedidos sincronizados sin rótulo</div>
      <button onClick={cargar} style={BTN_SEC}>↻ Recargar</button>
    </div>
    {loading&&<div style={{padding:10,fontSize:13,color:"#7a5a3a"}}><Spin/>Cargando…</div>}
    {err&&<div style={{padding:"10px",borderRadius:8,fontSize:13,background:"#fef2f2",border:"1.5px solid #f5b8b8",color:"#9b2020"}}>{err}</div>}
    {pedidos&&pedidos.length===0&&<div style={{padding:16,textAlign:"center",color:"#aaa",fontSize:13}}>No hay pedidos pendientes de importar.</div>}
    {pedidos&&pedidos.map(p=><div key={p.pedido_id} style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:10,padding:"10px 12px",border:"1.5px solid #e0d8cc",borderRadius:8,background:"#fff"}}>
      <div style={{minWidth:0}}>
        <div style={{fontWeight:700,fontSize:13,color:"#1c1a17",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{p.numero} · {p.nombres||"(sin nombre)"}</div>
        <div style={{fontSize:11,color:"#7a6a5a",whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{p.destino||"—"} · {p.celular||"—"}</div>
        <div style={{fontSize:11,color:"#9a8070"}}>{p.producto||"—"}</div>
      </div>
      <button onClick={()=>importar(p)} style={{...BTN,padding:"8px 14px",whiteSpace:"nowrap"}}>+ Importar</button>
    </div>)}
  </div>);
}

function EditModal({order,onSave,onClose,products}){
  const[f,setF]=useState({...order});const set=(k,v)=>setF(p=>({...p,[k]:v}));
  return(<div style={MODAL} onClick={onClose}>
    <div onClick={e=>e.stopPropagation()} style={{...MODAL_BOX,maxWidth:480}}>
      <div style={MODAL_HEAD}><span style={MODAL_TITLE}>✎ Editar rótulo</span><button onClick={onClose} style={X}>×</button></div>
      <div style={{padding:"16px 18px",display:"flex",flexDirection:"column",gap:12,overflowY:"auto"}}><CamposPedido f={f} set={set} products={products}/></div>
      <div style={MODAL_FOOT}><button onClick={onClose} style={BTN_SEC}>Cancelar</button><button onClick={()=>onSave(f)} style={BTN}>Guardar</button></div>
    </div>
  </div>);
}

function PrintModal({orders,totalPages,cfg,logoUrl,onClose}){
  const[pp,setPp]=useState(1);const[all,setAll]=useState(true);
  return(<div style={MODAL} onClick={onClose}>
    <div onClick={e=>e.stopPropagation()} style={{...MODAL_BOX,maxWidth:440}}>
      <div style={MODAL_HEAD}><span style={MODAL_TITLE}>🖨 Imprimir / PDF</span><button onClick={onClose} style={X}>×</button></div>
      <div style={{padding:"16px 18px",display:"flex",flexDirection:"column",gap:12}}>
        <div style={{display:"flex",gap:8}}>
          <button onClick={()=>setAll(false)} style={{flex:1,padding:11,border:`2px solid ${!all?"#1c1a17":"#d0c8bc"}`,borderRadius:8,background:!all?"#fff7ef":"#fff",fontWeight:700,cursor:"pointer"}}>Hoja {pp}</button>
          <button onClick={()=>setAll(true)} style={{flex:1,padding:11,border:`2px solid ${all?"#1c1a17":"#d0c8bc"}`,borderRadius:8,background:all?"#fff7ef":"#fff",fontWeight:700,cursor:"pointer"}}>Todas ({totalPages})</button>
        </div>
        {!all&&totalPages>1&&<div style={{display:"flex",gap:6,flexWrap:"wrap"}}>{Array.from({length:totalPages},(_,i)=>i+1).map(p=><button key={p} onClick={()=>setPp(p)} style={{padding:"6px 14px",border:`1.5px solid ${pp===p?"#c0532a":"#d0c8bc"}`,borderRadius:6,background:pp===p?"#fff7ef":"#fff",cursor:"pointer"}}>Hoja {p}</button>)}</div>}
        <div style={{padding:"10px 12px",background:"#fffbf0",borderRadius:8,fontSize:12.5,color:"#7a5a1a",border:"1px solid #e8d090"}}>💡 Para PDF: elige "Guardar como PDF", papel A4, márgenes Ninguno.</div>
      </div>
      <div style={MODAL_FOOT}><button onClick={onClose} style={BTN_SEC}>Cerrar</button><button onClick={()=>{doPrint(orders,pp,all,totalPages,cfg,logoUrl);onClose();}} style={BTN}>🖨 Imprimir</button></div>
    </div>
  </div>);
}

function ShalomModal({orders,products,onClose}){
  const go=()=>{exportarFormatoShalom(orders,products);onClose();};
  return(<div style={MODAL} onClick={onClose}>
    <div onClick={e=>e.stopPropagation()} style={{...MODAL_BOX,maxWidth:420}}>
      <div style={MODAL_HEAD}><span style={MODAL_TITLE}>📦 Exportar Shalom</span><button onClick={onClose} style={X}>×</button></div>
      <div style={{padding:"16px 18px",fontSize:13,color:"#5a4a3a"}}>Se exportarán <strong>{orders.length}</strong> pedido(s) al formato Shalom (.xlsx), mapeando destino y mercadería automáticamente.</div>
      <div style={MODAL_FOOT}><button onClick={onClose} style={BTN_SEC}>Cancelar</button><button onClick={go} disabled={!orders.length} style={{...BTN,background:!orders.length?"#c8a090":"#d4820a"}}>📦 Exportar .xlsx</button></div>
    </div>
  </div>);
}

const MERCS=["PAQUETE XXS","SOBRE","PAQUETE XS","PAQUETE S","PAQUETE M","PAQUETE L"];
function SettingsModal({cfg,setCfg,logos,setLogos,activeLogo,setActiveLogo,products,setProducts,ai,setAi,onSave,onClose}){
  const[tab,setTab]=useState("marca");const fileRef=useRef(null);
  const set=(k,v)=>setCfg(p=>({...p,[k]:v}));
  const[newNombre,setNewNombre]=useState("");const[newMerc,setNewMerc]=useState("PAQUETE XS");
  const handleLogo=async f=>{if(!f)return;const d=await f2url(f);const nl={id:Date.now(),name:f.name.replace(/\.[^.]+$/,""),dataUrl:d};const u=[...logos,nl];setLogos(u);setActiveLogo(nl.id);};
  const TABS=[["marca","🏷 Marca"],["visual","🎨 Visual"],["logos","🖼 Logos"],["productos","📦 Productos"],["ai","🤖 IA"]];
  const Toggle=({label,k})=>(<div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"9px 11px",border:"1px solid #e0d8cc",borderRadius:8,background:"#fff"}}><span style={{fontSize:14,fontWeight:600,color:"#3a2a1a"}}>{label}</span><div onClick={()=>set(k,!cfg[k])} style={{width:34,height:20,borderRadius:999,background:cfg[k]?"#1c1a17":"#d4cfc4",position:"relative",cursor:"pointer"}}><div style={{position:"absolute",top:3,left:cfg[k]?17:3,width:14,height:14,borderRadius:"50%",background:"#fff"}}/></div></div>);
  const Slider=({label,k,min,max})=>(<div><div style={{display:"flex",justifyContent:"space-between"}}><span style={{fontSize:13,fontWeight:600,color:"#5a4a3a"}}>{label}</span><span style={{fontSize:12,fontFamily:"monospace",color:"#9a8070"}}>{cfg[k]}</span></div><input type="range" min={min} max={max} value={cfg[k]} onChange={e=>set(k,Number(e.target.value))} style={{width:"100%",accentColor:"#c0532a"}}/></div>);
  return(<div style={{position:"fixed",inset:0,background:"#fdfaf6",zIndex:120,display:"flex",flexDirection:"column"}}>
    <div style={MODAL_HEAD}><span style={MODAL_TITLE}>⚙ Configuración</span><div style={{display:"flex",gap:8}}><button onClick={onSave} style={BTN}>Guardar</button><button onClick={onClose} style={BTN_SEC}>← Volver</button></div></div>
    <div style={{display:"flex",borderBottom:"1px solid #e0d8cc",background:"#f5f0e8",overflowX:"auto"}}>{TABS.map(([id,l])=><button key={id} onClick={()=>setTab(id)} style={{padding:"10px 14px",border:"none",borderBottom:`3px solid ${tab===id?"#c0532a":"transparent"}`,background:"transparent",fontSize:12,fontWeight:tab===id?700:500,color:tab===id?"#c0532a":"#7a6a5a",cursor:"pointer",whiteSpace:"nowrap"}}>{l}</button>)}</div>
    <div style={{flex:1,overflowY:"auto",padding:"16px 18px",maxWidth:620,width:"100%",margin:"0 auto",display:"flex",flexDirection:"column",gap:14}}>
      {tab==="marca"&&<>
        <div style={{display:"grid",gridTemplateColumns:"1fr 72px",gap:10}}>
          <div>{LBL("Nombre de marca")}<input value={cfg.brand} onChange={e=>set("brand",e.target.value)} style={I}/></div>
          <div>{LBL("Inicial")}<input value={cfg.initial} onChange={e=>set("initial",e.target.value.toUpperCase().slice(0,2))} maxLength={2} style={{...I,textAlign:"center",fontWeight:700}}/></div>
        </div>
        <div>{LBL("Color de acento")}<div style={{display:"flex",gap:8,flexWrap:"wrap"}}>{PALETTE.map(h=><div key={h} onClick={()=>set("accent",h)} style={{width:34,height:34,borderRadius:7,background:h,cursor:"pointer",border:cfg.accent===h?"3px solid #1a1a1a":"2px solid transparent"}}/>)}<input type="color" value={cfg.accent} onChange={e=>set("accent",e.target.value)} style={{width:34,height:34,borderRadius:7,border:"1.5px solid #bbb",cursor:"pointer"}}/></div></div>
      </>}
      {tab==="visual"&&<>
        <div>{LBL("Estilo")}<div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8}}>{[["classic","Clásico"],["bold","Negrita"],["minimal","Mínimo"]].map(([v,n])=><div key={v} onClick={()=>set("labelStyle",v)} style={{border:`2px solid ${cfg.labelStyle===v?"#1c1a17":"#d0c8bc"}`,borderRadius:9,padding:"12px 8px",cursor:"pointer",background:cfg.labelStyle===v?"#fff7ef":"#fff",textAlign:"center",fontWeight:700,fontSize:13}}>{n}</div>)}</div></div>
        <Slider label="Tamaño nombre" k="nameFontSize" min={11} max={20}/>
        <Slider label="Barra acento" k="accentBarHeight" min={0} max={10}/>
        <Toggle label="Código de barras" k="showBarcode"/><Toggle label="Texto Frágil" k="showFragile"/><Toggle label="Contador #01/06" k="showCounter"/>
      </>}
      {tab==="logos"&&<>
        {logos.length>0&&<div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:8}}>{logos.map(l=><div key={l.id} onClick={()=>setActiveLogo(activeLogo===l.id?null:l.id)} style={{border:`2px solid ${activeLogo===l.id?"#1c1a17":"#d0c8bc"}`,borderRadius:9,padding:8,cursor:"pointer",background:activeLogo===l.id?"#fff7ef":"#fff",textAlign:"center"}}><img src={l.dataUrl} style={{height:40,maxWidth:"100%",objectFit:"contain"}}/><div style={{fontSize:11,marginTop:4,whiteSpace:"nowrap",overflow:"hidden",textOverflow:"ellipsis"}}>{l.name}</div><button onClick={e=>{e.stopPropagation();const u=logos.filter(x=>x.id!==l.id);setLogos(u);if(activeLogo===l.id)setActiveLogo(null);}} style={{marginTop:4,padding:"2px 8px",background:"#fef2f2",border:"1px solid #f5b8b8",borderRadius:5,fontSize:11,color:"#9b2020",cursor:"pointer"}}>Eliminar</button></div>)}</div>}
        <div onClick={()=>fileRef.current?.click()} style={{border:"2px dashed #c8b8a8",borderRadius:9,padding:16,textAlign:"center",cursor:"pointer",background:"#faf7f3",fontSize:14,color:"#8a7060"}}>+ Subir logo</div>
        <input ref={fileRef} type="file" accept="image/*" onChange={e=>{handleLogo(e.target.files?.[0]);e.target.value="";}} style={{display:"none"}}/>
      </>}
      {tab==="productos"&&<>
        <div style={{fontSize:12,color:"#7a4a00",background:"#fff7ef",padding:"9px 11px",borderRadius:8,border:"1px solid #e8c880"}}>Define productos y su categoría Shalom (mercadería) para el export.</div>
        {products.map((p,i)=><div key={i} style={{display:"grid",gridTemplateColumns:"1fr auto auto",gap:8,alignItems:"center"}}>
          <input value={p.nombre} onChange={e=>{const u=[...products];u[i]={...u[i],nombre:e.target.value.toUpperCase()};setProducts(u);}} style={I}/>
          <select value={p.mercaderia} onChange={e=>{const u=[...products];u[i]={...u[i],mercaderia:e.target.value};setProducts(u);}} style={{...I,width:"auto"}}>{MERCS.map(m=><option key={m}>{m}</option>)}</select>
          <button onClick={()=>setProducts(products.filter((_,j)=>j!==i))} style={{...BTN_SEC,color:"#c04040",padding:"8px 12px"}}>×</button>
        </div>)}
        <div style={{display:"grid",gridTemplateColumns:"1fr auto auto",gap:8}}>
          <input value={newNombre} onChange={e=>setNewNombre(e.target.value)} placeholder="Nuevo producto" style={I}/>
          <select value={newMerc} onChange={e=>setNewMerc(e.target.value)} style={{...I,width:"auto"}}>{MERCS.map(m=><option key={m}>{m}</option>)}</select>
          <button onClick={()=>{if(!newNombre.trim())return;setProducts([...products,{nombre:newNombre.trim().toUpperCase(),mercaderia:newMerc}]);setNewNombre("");}} style={{...BTN,background:"#2f6b3b"}}>+</button>
        </div>
      </>}
      {tab==="ai"&&<>
        <div style={{fontSize:12,color:"#1a4a7a",background:"#f0f8ff",padding:"9px 11px",borderRadius:8,border:"1px solid #b0d0f0"}}>🔒 La API key se guarda cifrada en el servidor; no se expone en el navegador.</div>
        <div>{LBL("Modelo")}<input value={ai.ai_model} onChange={e=>setAi(p=>({...p,ai_model:e.target.value}))} placeholder="claude-haiku-4-5-20251001" style={I}/></div>
        <div>{LBL(ai.ai_key_set?`API key (actual: ${ai.ai_key_mask})`:"API key")}<input type="password" value={ai.ai_api_key||""} onChange={e=>setAi(p=>({...p,ai_api_key:e.target.value}))} placeholder={ai.ai_key_set?"(sin cambios)":"sk-ant-…"} style={I}/></div>
        <div>{LBL("Prompt de extracción")}<textarea value={ai.prompt} onChange={e=>setAi(p=>({...p,prompt:e.target.value}))} style={{...I,minHeight:120,fontFamily:"monospace",resize:"vertical"}}/></div>
      </>}
    </div>
  </div>);
}

// ── Estilos compartidos de modales ──
const MODAL={position:"fixed",inset:0,background:"rgba(0,0,0,0.55)",display:"flex",alignItems:"center",justifyContent:"center",padding:16,zIndex:150};
const MODAL_BOX={background:"#fdfaf6",borderRadius:14,width:"100%",maxHeight:"92vh",display:"flex",flexDirection:"column",border:"1.5px solid #d0c8bc"};
const MODAL_HEAD={display:"flex",alignItems:"center",justifyContent:"space-between",padding:"13px 18px",borderBottom:"1px solid #e0d8cc",background:"#f5f0e8"};
const MODAL_TITLE={fontSize:15,fontWeight:700,color:"#3a2a1a"};
const MODAL_FOOT={padding:"12px 18px",borderTop:"1px solid #e0d8cc",background:"#f5f0e8",display:"flex",justifyContent:"flex-end",gap:8};
const X={background:"none",border:"none",fontSize:22,cursor:"pointer",color:"#888",lineHeight:1};

// Preview de etiqueta en pantalla
function LabelCard({order,cfg,logoUrl}){
  const hBg=cfg.labelStyle==="bold"?cfg.accent:(cfg.headerBg||"#fdfcfa");
  const hCol=cfg.labelStyle==="bold"?"#fff":"#1c1a17";
  return(<div style={{border:cfg.labelStyle==="minimal"?"1px solid #d0ccc4":"1.5px solid #1c1a17",borderRadius:8,overflow:"hidden",background:"#fff",fontSize:11}}>
    <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"6px 9px",background:hBg,borderBottom:"1px solid #1c1a17"}}>
      <div style={{display:"flex",alignItems:"center",gap:6}}>{logoUrl?<img src={logoUrl} style={{height:16,maxWidth:54,objectFit:"contain"}}/>:<span style={{width:16,height:16,borderRadius:3,background:cfg.accent,color:"#fff",fontWeight:700,fontSize:10,display:"flex",alignItems:"center",justifyContent:"center"}}>{cfg.initial}</span>}<span style={{fontWeight:700,fontSize:11,textTransform:"uppercase",color:hCol}}>{cfg.brand}</span></div>
    </div>
    <div style={{padding:"6px 9px",borderBottom:"1px dashed #ccc"}}><div style={{fontSize:8,textTransform:"uppercase",color:"#999",fontWeight:600}}>Destinatario</div><div style={{fontWeight:700}}>{order.nombres||"—"}</div></div>
    <div style={{padding:"6px 9px",borderBottom:"1px dashed #ccc"}}><div style={{fontSize:8,textTransform:"uppercase",color:"#999",fontWeight:600}}>Dirección</div><div>{order.destino||"—"}</div></div>
    <div style={{display:"grid",gridTemplateColumns:"1fr 1fr"}}>
      <div style={{padding:"6px 9px",borderRight:"1px dashed #ccc"}}><div style={{fontSize:8,textTransform:"uppercase",color:"#999",fontWeight:600}}>Agencia</div><div style={{fontSize:10}}>{order.agencia||"—"}</div></div>
      <div style={{padding:"6px 9px"}}><div style={{fontSize:8,textTransform:"uppercase",color:"#999",fontWeight:600}}>Celular</div><div style={{fontFamily:"monospace",fontWeight:700}}>{order.celular||"—"}</div></div>
    </div>
  </div>);
}

// ── App ──
function App(){
  const[cfg,setCfg]=useState(null);          // config flat (incl. visual)
  const[logos,setLogos]=useState([]);
  const[activeLogo,setActiveLogo]=useState(null);
  const[products,setProducts]=useState([]);
  const[ai,setAi]=useState({ai_provider:"anthropic",ai_model:"",ai_api_key:"",ai_key_set:false,ai_key_mask:"",prompt:""});
  const[orders,setOrders]=useState([]);
  const[tab,setTab]=useState("import");
  const[editing,setEditing]=useState(null);
  const[showSettings,setShowSettings]=useState(false);
  const[printOpen,setPrintOpen]=useState(false);
  const[shalomOpen,setShalomOpen]=useState(false);

  useEffect(()=>{(async()=>{
    try{
      const c=await API.config();
      setCfg({brand:c.brand,initial:c.initial,accent:c.accent,labelStyle:c.label_style,...c.visual});
      setLogos(c.logos||[]);setActiveLogo(c.active_logo);setProducts(c.productos||[]);
      setAi({ai_provider:c.ai_provider,ai_model:c.ai_model,ai_api_key:"",ai_key_set:c.ai_key_set,ai_key_mask:c.ai_key_mask,prompt:c.prompt});
      const r=await API.rotulos();setOrders(r.rotulos);
    }catch(e){alert("Error cargando: "+e.message);}
  })();},[]);

  const logoUrl=useMemo(()=>(logos.find(l=>l.id===activeLogo)||{}).dataUrl||null,[logos,activeLogo]);
  const totalPages=Math.max(1,Math.ceil(orders.length/PER_PAGE));

  const addOrder=async d=>{try{const o=await API.crear(d);setOrders(p=>[o,...p]);}catch(e){alert(e.message);}};
  const saveOrder=async f=>{try{const o=await API.editar(f.id,f);setOrders(p=>p.map(x=>x.id===o.id?o:x));setEditing(null);}catch(e){alert(e.message);}};
  const delOrder=async id=>{if(!confirm("¿Eliminar este rótulo?"))return;try{await API.borrar(id);setOrders(p=>p.filter(x=>x.id!==id));}catch(e){alert(e.message);}};

  const saveSettings=async()=>{
    try{
      const visual={headerBg:cfg.headerBg,footerBg:cfg.footerBg,bodyBg:cfg.bodyBg,nameFontSize:cfg.nameFontSize,accentBarHeight:cfg.accentBarHeight,borderRadius:cfg.borderRadius,showBarcode:cfg.showBarcode,showCutMarks:cfg.showCutMarks,showFragile:cfg.showFragile,showCounter:cfg.showCounter};
      const payload={brand:cfg.brand,initial:cfg.initial,accent:cfg.accent,label_style:cfg.labelStyle,visual,logos,active_logo:activeLogo,productos:products,ai_provider:ai.ai_provider,ai_model:ai.ai_model,prompt:ai.prompt};
      if((ai.ai_api_key||"").trim())payload.ai_api_key=ai.ai_api_key.trim();
      const c=await API.saveConfig(payload);
      setAi(p=>({...p,ai_api_key:"",ai_key_set:c.ai_key_set,ai_key_mask:c.ai_key_mask}));
      setShowSettings(false);
    }catch(e){alert(e.message);}
  };

  if(!cfg)return<div className="rot-loading">Cargando rotulador…</div>;

  const tabs=[["import","📥 Importar"],["paste","📋 Mensaje"],["foto","📷 Foto"],["form","✍ Manual"]];
  return(<div style={{display:"grid",gridTemplateColumns:"minmax(320px,380px) 1fr",gap:18,alignItems:"start"}}>
    {/* Panel izquierdo: entradas */}
    <div style={{background:"#fff",border:"1px solid var(--border)",borderRadius:12,padding:16,boxShadow:"var(--shadow)"}}>
      <div style={{display:"flex",gap:6,marginBottom:12,flexWrap:"wrap"}}>{tabs.map(([id,l])=><button key={id} onClick={()=>setTab(id)} style={{padding:"7px 11px",border:`1.5px solid ${tab===id?"#c0532a":"#e0d8cc"}`,borderRadius:8,background:tab===id?"#fff7ef":"#fff",fontSize:12.5,fontWeight:tab===id?700:500,color:tab===id?"#c0532a":"#6a5a4a",cursor:"pointer"}}>{l}</button>)}</div>
      {tab==="import"&&<ImportTab onImport={addOrder}/>}
      {tab==="paste"&&<PasteTab onAdd={addOrder} products={products}/>}
      {tab==="foto"&&<FotoTab onAdd={addOrder} products={products}/>}
      {tab==="form"&&<FormTab onAdd={addOrder} products={products}/>}
    </div>

    {/* Panel derecho: lista + acciones */}
    <div>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:12,flexWrap:"wrap",gap:8}}>
        <div style={{fontSize:14,fontWeight:700,color:"var(--text)"}}>Rótulos ({orders.length}) · {totalPages} hoja(s)</div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          <button onClick={()=>setShowSettings(true)} style={BTN_SEC}>⚙ Configuración</button>
          <button onClick={()=>setShalomOpen(true)} disabled={!orders.length} style={{...BTN,background:!orders.length?"#c8a090":"#d4820a"}}>📦 Shalom</button>
          <button onClick={()=>setPrintOpen(true)} disabled={!orders.length} style={{...BTN,background:!orders.length?"#c8a090":"#c0532a"}}>🖨 Imprimir</button>
        </div>
      </div>
      {orders.length===0?<div style={{padding:40,textAlign:"center",color:"#aaa",fontSize:14,background:"#fff",borderRadius:12,border:"1px dashed #d0ccc4"}}>Sin rótulos. Importa pedidos o agrega uno por mensaje/manual.</div>:
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(220px,1fr))",gap:12}}>
        {orders.map(o=><div key={o.id} style={{position:"relative"}}>
          <LabelCard order={o} cfg={cfg} logoUrl={logoUrl}/>
          <div style={{display:"flex",gap:6,marginTop:6}}>
            <button onClick={()=>setEditing(o)} style={{...BTN_SEC,flex:1,padding:"6px"}}>✎ Editar</button>
            <button onClick={()=>delOrder(o.id)} style={{...BTN_SEC,color:"#c04040",padding:"6px 10px"}}>🗑</button>
          </div>
        </div>)}
      </div>}
    </div>

    {editing&&<EditModal order={editing} products={products} onSave={saveOrder} onClose={()=>setEditing(null)}/>}
    {printOpen&&<PrintModal orders={orders} totalPages={totalPages} cfg={cfg} logoUrl={logoUrl} onClose={()=>setPrintOpen(false)}/>}
    {shalomOpen&&<ShalomModal orders={orders} products={products} onClose={()=>setShalomOpen(false)}/>}
    {showSettings&&<SettingsModal cfg={cfg} setCfg={setCfg} logos={logos} setLogos={setLogos} activeLogo={activeLogo} setActiveLogo={setActiveLogo} products={products} setProducts={setProducts} ai={ai} setAi={setAi} onSave={saveSettings} onClose={()=>setShowSettings(false)}/>}
  </div>);
}

ReactDOM.createRoot(document.getElementById("rot-root")).render(<App/>);
