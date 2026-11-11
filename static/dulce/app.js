/* Interfaz compartida. La API valida permisos, precios y disponibilidad. */
const D = window.D = {
  user:null,recipes:[],
  esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));},
  money(v){return new Intl.NumberFormat('es-CL',{style:'currency',currency:'CLP',maximumFractionDigits:0}).format(Number(v));},
  date(v){return new Intl.DateTimeFormat('es-CL',{dateStyle:'medium',timeStyle:'short',timeZone:'America/Santiago'}).format(new Date(v));},
  error(v){if(typeof v==='string')return v;if(Array.isArray(v))return v.map(x=>D.error(x)).join('\n');return Object.entries(v||{}).map(([k,x])=>`${k==='detail'?'':k+': '}${D.error(x)}`).join('\n');},
  async api(path,method='GET',data){
    const csrf=document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=').slice(1).join('=')||document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    const r=await fetch('/api/'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json',...(csrf?{'X-CSRFToken':csrf}:{})},...(data!==undefined?{body:JSON.stringify(data)}:{})});
    const text=await r.text();let result;try{result=text?JSON.parse(text):null;}catch{throw Error('No se pudo completar la operación. Recarga la página e inténtalo otra vez.');}
    if(!r.ok)throw Error(D.error(result));return result;
  },
  toast(msg){const el=document.querySelector('#toast');el.textContent=msg;el.hidden=false;clearTimeout(D.timer);D.timer=setTimeout(()=>el.hidden=true,5000);},
  modal(html){document.querySelector('#modal-body').innerHTML=html;const m=document.querySelector('#modal');if(!m.open)m.showModal();},
  close(){document.querySelector('#modal').close();},
  badge(p){const c=['LISTO','RETIRADO'].includes(p.estado)?'green':p.estado==='CANCELADO'?'gray':'pink';return `<span class="badge ${c}">${D.esc(p.etiqueta||p.estado)}</span>`;},
  progress(p){const steps=['RECIBIDO','PREPARACION','HORNEADO','CALIDAD','LISTO','RETIRADO'];const pos=steps.indexOf(p.estado);return `<div class="status-progress" aria-label="${D.esc(p.etiqueta)}">${steps.map((s,i)=>`<span class="${i<=pos?'done':''}"></span>`).join('')}</div>`;},
  timeline(p){return `<ol class="timeline">${p.historial.map(h=>`<li><strong>${D.esc(h.etiqueta)}</strong><small>${D.date(h.creado)}</small>${h.detalle?`<span>${D.esc(h.detalle)}</span>`:''}</li>`).join('')}</ol>`;}
};
document.addEventListener('DOMContentLoaded',async()=>{
  document.querySelector('.modal-close').onclick=D.close;
  document.querySelector('#modal').addEventListener('click',e=>{if(e.target===e.currentTarget){const b=e.currentTarget.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)D.close();}});
  try{
    D.user=(await D.api('cuenta/')).usuario;
    if(D.user){document.querySelector('#account-link').textContent=D.user.nombre;document.querySelector('#account-link').href='/mis-pedidos/';document.querySelector('#logout').hidden=false;}
    document.querySelector('#logout').onclick=async()=>{try{await D.api('cuenta/','POST',{modo:'logout'});location.href='/';}catch(e){D.toast(e.message);}};
    const page=document.body.dataset.page;
    if(page==='inicio')await initCatalog();
    if(page==='cuenta')initAuth();
    if(page==='pedidos')await loadOrders();
    if(page==='seguimiento')await tracking();
    if(page==='equipo')await window.initEquipo();
  }catch(e){D.toast(e.message);const target=document.querySelector('#products,#work-content,#my-orders,#tracking-content');if(target)target.innerHTML=`<p class="empty">${D.esc(e.message)} <button class="text-link" onclick="location.reload()">Reintentar</button></p>`;}
});
async function initCatalog(){
  D.recipes=await D.api('recetas/');let category='Todas';
  function draw(){const search=document.querySelector('#search').value.toLocaleLowerCase('es');const items=D.recipes.filter(r=>(category==='Todas'||r.categoria===category)&&(r.nombre+' '+r.descripcion).toLocaleLowerCase('es').includes(search));
    document.querySelector('#products').innerHTML=items.length?items.map(r=>`<article class="product-card ${r.disponible?'':'unavailable'}"><div class="product-image"><img src="/static/dulce/${D.esc(r.imagen)}" alt="${D.esc(r.nombre)}" loading="lazy"><span class="badge ${r.disponible?'':'gray'}">${r.disponible?'Hecho por encargo':'Por ahora, agotado'}</span></div><div class="product-body"><span class="category">${D.esc(r.categoria)} · ${r.porciones} porciones</span><h3>${D.esc(r.nombre)}</h3><p>${D.esc(r.descripcion)}</p><div class="product-bottom"><div><strong>${D.money(r.precio)}</strong><small>Preparado para compartir</small></div><button data-order="${r.id}" ${r.disponible?'':'disabled'} aria-label="Encargar ${D.esc(r.nombre)}">↗</button></div></div></article>`).join(''):'<p class="empty">No encontramos ese antojo. Prueba con otro nombre.</p>';
    document.querySelectorAll('[data-order]').forEach(b=>b.onclick=()=>orderModal(Number(b.dataset.order)));
  }
  document.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{category=b.dataset.category;document.querySelectorAll('[data-category]').forEach(x=>x.classList.toggle('active',x===b));draw();});document.querySelector('#search').oninput=draw;draw();const selected=Number(new URLSearchParams(location.search).get('producto'));if(D.user&&D.recipes.some(r=>r.id===selected&&r.disponible))orderModal(selected);
}
function orderModal(id){
  if(!D.user){location.href='/cuenta/?producto='+id;return;}
  const r=D.recipes.find(x=>x.id===id),key=crypto.randomUUID();
  const future=new Date(Date.now()+2*86400000);const day=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'2-digit',day:'2-digit'}).format(future);
  D.modal(`<div class="modal-product"><img src="/static/dulce/${D.esc(r.imagen)}" alt=""><div><span class="eyebrow">TU PRÓXIMO MOMENTO DULCE</span><h2>${D.esc(r.nombre)}</h2><p>${r.porciones} porciones · ${D.esc(r.alergenos)}</p></div></div><form id="order-form"><div class="field-row"><label>Cantidad<input name="cantidad" type="number" min="1" max="${Math.min(20,r.unidades_disponibles)}" value="1" required></label><label>Teléfono de contacto<input name="telefono" type="tel" placeholder="+56 9 1234 5678" required maxlength="25"></label></div><div class="field-row"><label>Día de retiro<input name="fecha" type="date" value="${day}" required></label><label>Hora de retiro<input name="hora" type="time" min="10:00" max="18:59" value="12:00" required></label></div><label>Tu idea de decoración <span class="muted">(opcional)</span><textarea name="diseno" maxlength="1500" placeholder="Una frase, colores, una ocasión especial…"></textarea></label><label>Preferencias de ingredientes <span class="muted">(opcional)</span><input name="preferencias" maxlength="1500" placeholder="Cuéntanos qué te gustaría cambiar"></label><p class="small-text muted">Contiene: ${D.esc(r.alergenos||'Consulta al equipo')}. Elaboramos en una cocina compartida. Las modificaciones se revisan antes de confirmar.</p><div class="notice">Retiro en el local, de 10:00 a 19:00. Pago al retirar. Los pedidos personalizados requieren una cotización aprobada por ti.</div><div class="modal-total"><span id="total-label">Total del pedido</span><strong id="order-total">${D.money(r.precio)}</strong></div><p id="order-error" class="form-error" role="alert"></p><button class="button full" id="order-submit">Confirmar pedido →</button></form>`);
  const form=document.querySelector('#order-form');
  form.oninput=()=>{const custom=!!(form.diseno.value.trim()||form.preferencias.value.trim());document.querySelector('#order-total').textContent=D.money(r.precio*Number(form.cantidad.value));document.querySelector('#total-label').textContent=custom?'Precio base estimado':'Total del pedido';document.querySelector('#order-submit').textContent=custom?'Solicitar cotización →':'Confirmar pedido →';};
  form.onsubmit=async e=>{e.preventDefault();const b=document.querySelector('#order-submit');b.disabled=true;
    try{const f=Object.fromEntries(new FormData(form));const result=await D.api('pedidos/','POST',{receta:id,cantidad:Number(f.cantidad),telefono:f.telefono,retiro:f.fecha+'T'+f.hora+':00',diseno:f.diseno,preferencias:f.preferencias,solicitud:key});D.close();location.href='/mis-pedidos/?nuevo='+result.id;}catch(err){document.querySelector('#order-error').textContent=err.message;b.disabled=false;}
  };
}
function initAuth(){
  let registering=false;const form=document.querySelector('#auth-form');
  document.querySelector('#register-toggle').onclick=()=>{registering=!registering;document.querySelector('#name-label').hidden=!registering;form.nombre.required=registering;document.querySelector('#auth-title').textContent=registering?'Tu rincón dulce.':'Qué gusto verte.';document.querySelector('#auth-description').textContent=registering?'Crea tu cuenta y empieza a compartir cosas ricas.':'Ingresa para encargar y seguir tus pedidos.';document.querySelector('#register-toggle').textContent=registering?'Ya tengo cuenta':'Regístrate aquí';form.querySelector('button').textContent=registering?'Crear mi cuenta →':'Entrar a mi cuenta →';form.password.autocomplete=registering?'new-password':'current-password';};
  form.onsubmit=async e=>{e.preventDefault();const button=form.querySelector('button');button.disabled=true;try{const data=Object.fromEntries(new FormData(form));data.modo=registering?'registro':'login';const r=await D.api('cuenta/','POST',data);const params=new URLSearchParams(location.search);location.href=r.usuario.equipo?'/equipo/':params.has('producto')?'/?producto='+params.get('producto'):'/mis-pedidos/';}catch(err){document.querySelector('#auth-error').textContent=err.message;button.disabled=false;}};
}
async function loadOrders(){
  const orders=await D.api('pedidos/');
  document.querySelector('#my-orders').innerHTML=orders.length?orders.map(p=>`<article class="order-card"><div class="order-header"><div><span class="eyebrow">${p.codigo}</span><h3>${D.esc(p.producto)} <span class="muted">× ${p.cantidad}</span></h3></div>${D.badge(p)}</div>${D.progress(p)}<div class="order-meta"><span>Retiro: ${D.date(p.retiro)}</span><span>${p.estado==='COTIZACION'?'Precio base: ':''}${D.money(p.total)}</span><span>${p.pagado?'Pago recibido':'Pago al retirar'}</span></div>${p.nota_equipo?`<div class="notice"><strong>El equipo te cuenta:</strong> ${D.esc(p.nota_equipo)}</div>`:''}${p.diseno||p.preferencias?`<p class="small-text muted">Tu idea: ${D.esc([p.diseno,p.preferencias].filter(Boolean).join(' · '))}</p>`:''}<div class="order-actions">${p.estado==='COTIZADO'?`<button class="button small rose" data-accept="${p.id}">Aceptar cotización · ${D.money(p.total)}</button>`:''}<button class="button small outline" data-detail="${p.id}">Ver seguimiento y QR</button><a class="text-link" href="/api/pedidos/${p.id}/comprobante/">Descargar comprobante</a>${['COTIZACION','COTIZADO','RECIBIDO'].includes(p.estado)?`<button class="text-link" data-cancel="${p.id}">Cancelar pedido</button>`:''}</div></article>`).join(''):'<div class="empty"><h3>Aún no hay dulces por aquí.</h3><p>Tu primer pedido puede ser el comienzo de algo rico.</p><a class="button" href="/#vitrina">Explorar la vitrina →</a></div>';
  document.querySelectorAll('[data-detail]').forEach(b=>b.onclick=()=>{const p=orders.find(x=>x.id===Number(b.dataset.detail));D.modal(`<span class="eyebrow">${p.codigo}</span><h2>${D.esc(p.producto)}</h2>${D.badge(p)}${D.timeline(p)}${!['COTIZACION','COTIZADO','CANCELADO'].includes(p.estado)?`<img class="qr-large" src="/api/pedidos/${p.id}/qr/" alt="QR de retiro del pedido"><p class="small-text muted">Presenta este QR en el mesón. Es personal: no lo compartas.</p>`:'<p class="notice">El QR de retiro se muestra después de confirmar el pedido.</p>'}`);});
  document.querySelectorAll('[data-accept]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await D.api(`pedidos/${b.dataset.accept}/aceptar/`,'POST',{});await loadOrders();D.toast('Cotización aceptada. Tus ingredientes ya están reservados.');}catch(e){D.toast(e.message);b.disabled=false;}});
  document.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=()=>{D.modal('<h2>¿Cancelar este pedido?</h2><p>Se liberarán los ingredientes reservados. Esta acción no puede deshacerse.</p><button class="button danger" id="confirm-cancel">Sí, cancelar pedido</button>');document.querySelector('#confirm-cancel').onclick=async e=>{e.target.disabled=true;try{await D.api(`pedidos/${b.dataset.cancel}/estado/`,'POST',{estado:'CANCELADO'});D.close();await loadOrders();}catch(err){D.toast(err.message);e.target.disabled=false;}};});
}
async function tracking(){
  try{const p=await D.api('seguimiento/'+document.querySelector('.tracking').dataset.token+'/');document.querySelector('#tracking-content').innerHTML=`<span class="eyebrow">${p.codigo}</span><h2>${D.esc(p.producto)} × ${p.cantidad}</h2>${D.badge(p)}${D.progress(p)}<p>Retiro: ${D.date(p.retiro)}</p>${D.timeline(p)}${p.estado==='LISTO'?'<div class="notice">¡Ya está listo! Te esperamos en el mesón.</div>':''}`;}catch(e){document.querySelector('#tracking-content').innerHTML='<p>No encontramos este pedido. Revisa el enlace de tu correo.</p>';}
}
