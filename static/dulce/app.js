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
  cleanHashAndScroll();
  document.addEventListener('click',e=>{
    const link=e.target.closest('a[href*="#"]');if(!link)return;
    const url=new URL(link.href,location.href);if(url.origin!==location.origin||!url.hash||url.pathname!==location.pathname)return;
    const target=document.getElementById(decodeURIComponent(url.hash.slice(1)));if(!target)return;
    e.preventDefault();history.replaceState(null,'',location.pathname+location.search);target.scrollIntoView({behavior:'smooth',block:'start'});
  });
  document.querySelector('.modal-close').onclick=D.close;
  document.querySelector('#modal').addEventListener('click',e=>{if(e.target===e.currentTarget){const b=e.currentTarget.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)D.close();}});
  try{
    D.user=(await D.api('cuenta/')).usuario;
    if(D.user){const account=document.querySelector('#account-link');account.textContent=D.user.nombre;account.href=D.user.equipo?'/equipo/':'/mis-pedidos/';document.querySelector('#logout').hidden=false;}
    else document.querySelector('#account-link').textContent='Entrar';
    document.querySelector('#logout').onclick=async()=>{try{await D.api('cuenta/','POST',{modo:'logout'});location.href='/';}catch(e){D.toast(e.message);}};
    const page=document.body.dataset.page;
    if(page==='inicio')await initCatalog();
    if(page==='cuenta')initAuth();
    if(page==='pedidos')await loadOrders();
    if(page==='seguimiento')await tracking();
    if(page==='equipo')await window.initEquipo();
  }catch(e){D.toast(e.message);const target=document.querySelector('#products,#work-content,#my-orders,#tracking-content');if(target)target.innerHTML=`<p class="empty">${D.esc(e.message)} <button class="text-link" onclick="location.reload()">Reintentar</button></p>`;}
});
function cleanHashAndScroll(){
  if(!location.hash)return;
  const target=document.getElementById(decodeURIComponent(location.hash.slice(1)));
  history.replaceState(null,'',location.pathname+location.search);
  if(target)requestAnimationFrame(()=>target.scrollIntoView({behavior:'smooth',block:'start'}));
}
async function initCatalog(){
  D.recipes=await D.api('recetas/');let category='Todas';
  function draw(){
    const search=document.querySelector('#search').value.toLocaleLowerCase('es');
    const items=D.recipes.filter(r=>(category==='Todas'||r.categoria===category)&&(r.nombre+' '+r.descripcion).toLocaleLowerCase('es').includes(search));
    document.querySelector('#products').innerHTML=items.length?items.map(r=>`<article class="product-card ${r.disponible?'':'unavailable'}" data-product="${r.id}" tabindex="0" role="group" aria-label="${D.esc(r.nombre)}. Presiona Enter para ver sus detalles."><div class="product-image"><img src="/static/dulce/${D.esc(r.imagen)}" alt="${D.esc(r.nombre)}" loading="lazy"><span class="badge ${r.disponible?'':'gray'}">${r.disponible?'Hecho por encargo':'Por ahora, agotado'}</span></div><div class="product-body"><span class="category">${D.esc(r.categoria)} · ${r.porciones} porciones por unidad</span><h3>${D.esc(r.nombre)}</h3><p>${D.esc(r.descripcion)}</p><div class="product-bottom"><div><strong>${D.money(r.precio)}</strong><small>${r.porciones} porciones · ${r.minutos} min de preparación</small></div><button type="button" aria-label="Ver ingredientes y encargar ${D.esc(r.nombre)}">↗</button></div></div></article>`).join(''):'<p class="empty">No encontramos ese antojo. Prueba con otro nombre.</p>';
    document.querySelectorAll('[data-product]').forEach(card=>{
      card.onclick=e=>{if(e.target.closest('button'))e.preventDefault();showProduct(Number(card.dataset.product));};
      card.onkeydown=e=>{if(e.target===card&&(e.key==='Enter'||e.key===' ')){e.preventDefault();showProduct(Number(card.dataset.product));}};
    });
  }
  document.querySelectorAll('[data-category]').forEach(b=>b.onclick=()=>{category=b.dataset.category;document.querySelectorAll('[data-category]').forEach(x=>x.classList.toggle('active',x===b));draw();});
  document.querySelector('#search').oninput=draw;draw();
  const selected=Number(new URLSearchParams(location.search).get('producto'));
  if(D.user&&D.recipes.some(r=>r.id===selected&&r.disponible))orderModal(selected);
}
function productDetails(r){
  const ingredients=(r.ingredientes_publicos||[]).length?(r.ingredientes_publicos||[]).map(x=>`<li>${D.esc(x)}</li>`).join(''):'<li>Consulta los ingredientes con nuestro equipo.</li>';
  return `<div class="product-detail"><div class="product-detail-image"><img src="/static/dulce/${D.esc(r.imagen)}" alt="${D.esc(r.nombre)}"></div><div class="product-detail-copy"><span class="eyebrow">${D.esc(r.categoria)} · PASTELERÍA ARTESANAL</span><h2>${D.esc(r.nombre)}</h2><p>${D.esc(r.descripcion)}</p><div class="product-facts"><span>🍰 <strong>${r.porciones}</strong> porciones por unidad</span><span>⏱ <strong>${r.minutos}</strong> min de preparación</span></div><div class="product-ingredients"><h3>Hecho con</h3><ul>${ingredients}</ul></div><p class="product-allergens"><strong>Alérgenos:</strong> ${D.esc(r.alergenos||'Consulta al equipo')} · Elaborado en cocina compartida.</p><div class="product-detail-price"><span>Desde</span><strong>${D.money(r.precio)}</strong></div></div></div>`;
}
function showProduct(id){
  const r=D.recipes.find(x=>x.id===id);
  if(!r)return;
  if(D.user){orderModal(id);return;}
  const next=r.disponible?`<div class="product-detail-actions"><p>Para elegir las porciones y coordinar el retiro, entra o crea tu cuenta.</p><button class="button full" id="continue-to-account">Iniciar sesión o crear cuenta →</button></div>`:'<div class="notice">Por ahora no tenemos ingredientes suficientes para aceptar este pedido. Vuelve a revisar pronto.</div>';
  D.modal(`${productDetails(r)}${next}`);
  document.querySelector('#continue-to-account')?.addEventListener('click',()=>{location.href='/cuenta/?producto='+id;});
}
function newRequestId(){
  if(window.crypto&&typeof window.crypto.randomUUID==='function')return window.crypto.randomUUID();
  const bytes=new Uint8Array(16);
  if(window.crypto&&typeof window.crypto.getRandomValues==='function')window.crypto.getRandomValues(bytes);else for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256);
  bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const h=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
  return `${h.slice(0,8)}-${h.slice(8,12)}-${h.slice(12,16)}-${h.slice(16,20)}-${h.slice(20)}`;
}
function orderModal(id){
  const r=D.recipes.find(x=>x.id===id);if(!r||!D.user){showProduct(id);return;}if(!r.disponible){D.modal(`${productDetails(r)}<div class="notice">Por ahora no tenemos ingredientes suficientes para aceptar este pedido. Vuelve a revisar pronto.</div>`);return;}
  const servingsPerUnit=Math.max(1,Number(r.porciones)||1),maxUnits=Math.max(1,Math.min(20,Number(r.unidades_disponibles)||1));
  const options=Array.from({length:maxUnits},(_,i)=>{const units=i+1,servings=units*servingsPerUnit;return `<option value="${servings}">${servings} porciones · ${units} ${units===1?'unidad':'unidades'}</option>`;}).join('');
  const future=new Date(Date.now()+2*86400000);const day=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Santiago',year:'numeric',month:'2-digit',day:'2-digit'}).format(future);const key=newRequestId();
  D.modal(`${productDetails(r)}<form id="order-form"><div class="field-row"><label>Porciones que necesitas<select name="porciones" required>${options}</select><small>Cada unidad rinde ${servingsPerUnit} porciones; el stock se calcula por unidad completa.</small></label><label>Teléfono de contacto<input name="telefono" type="tel" placeholder="+56 9 1234 5678" required maxlength="25"></label></div><div class="field-row"><label>Día de retiro<input name="fecha" type="date" value="${day}" required></label><label>Hora de retiro<input name="hora" type="time" min="10:00" max="18:59" value="12:00" required></label></div><label>Tu idea de decoración <span class="muted">(opcional)</span><textarea name="diseno" maxlength="1500" placeholder="Una frase, colores, una ocasión especial…"></textarea></label><label>Preferencias de ingredientes <span class="muted">(opcional)</span><input name="preferencias" maxlength="1500" placeholder="Cuéntanos qué te gustaría cambiar"></label><p class="small-text muted">Alérgenos: ${D.esc(r.alergenos||'Consulta al equipo')}. Las modificaciones se revisan antes de confirmar.</p><div class="notice">Retiro en el local, de 10:00 a 19:00. Pago al retirar. Los pedidos personalizados requieren una cotización que aprobarás desde Mis compras.</div><div class="modal-total"><span id="total-label">Total del pedido</span><strong id="order-total">${D.money(r.precio)}</strong></div><p id="order-error" class="form-error" role="alert"></p><button class="button full" id="order-submit">Confirmar pedido →</button></form>`);
  const form=document.querySelector('#order-form');
  function updateOrder(){const units=Number(form.porciones.value)/servingsPerUnit,custom=!!(form.diseno.value.trim()||form.preferencias.value.trim());document.querySelector('#order-total').textContent=D.money(r.precio*units);document.querySelector('#total-label').textContent=custom?'Precio base estimado':'Total del pedido';document.querySelector('#order-submit').textContent=custom?'Solicitar cotización →':'Confirmar pedido →';}
  form.oninput=updateOrder;form.onchange=updateOrder;
  form.onsubmit=async e=>{e.preventDefault();const b=document.querySelector('#order-submit');b.disabled=true;
    try{const f=Object.fromEntries(new FormData(form));const quantity=Number(f.porciones)/servingsPerUnit;const result=await D.api('pedidos/','POST',{receta:id,cantidad:quantity,telefono:f.telefono,retiro:f.fecha+'T'+f.hora+':00',diseno:f.diseno,preferencias:f.preferencias,solicitud:key});D.close();location.href='/mis-pedidos/?nuevo='+result.id;}catch(err){document.querySelector('#order-error').textContent=err.message;b.disabled=false;}
  };
}
function initAuth(){
  const form=document.querySelector('#auth-form'),roleTabs=[...document.querySelectorAll('[data-role-tab]')],modeTabs=[...document.querySelectorAll('[data-mode-tab]')],params=new URLSearchParams(location.search);
  let role=params.has('equipo')?'admin':'cliente',mode='login';
  const nameLabel=document.querySelector('#name-label'),modeTabsBox=document.querySelector('#auth-mode-tabs'),error=document.querySelector('#auth-error'),submit=document.querySelector('#auth-submit');
  function render(){
    const admin=role==='admin',registering=!admin&&mode==='registro';
    roleTabs.forEach(b=>{const selected=b.dataset.roleTab===role;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected));});
    modeTabsBox.hidden=admin;modeTabs.forEach(b=>{const selected=b.dataset.modeTab===mode;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected));});
    nameLabel.hidden=!registering;form.nombre.required=registering;form.nombre.disabled=!registering;
    document.querySelector('#auth-eyebrow').textContent=admin?'ACCESO DEL EQUIPO':'TU RINCÓN DULCE';
    document.querySelector('#auth-title').textContent=registering?'Crea tu cuenta.':admin?'Bienvenida al taller.':'Qué gusto verte.';
    document.querySelector('#auth-description').textContent=admin?'Ingresa con la cuenta de administración del local.':'Inicia sesión o crea tu cuenta para encargar y seguir tus compras.';
    document.querySelector('#auth-hint').textContent=admin?'Sólo las cuentas autorizadas por el local pueden entrar al taller.':'Tu cuenta de cliente sólo muestra tus compras.';
    submit.textContent=registering?'Crear mi cuenta →':admin?'Entrar a administración →':'Entrar a mi cuenta →';
    form.password.autocomplete=registering?'new-password':'current-password';error.textContent='';
  }
  roleTabs.forEach(b=>b.onclick=()=>{role=b.dataset.roleTab;mode='login';render();});
  modeTabs.forEach(b=>b.onclick=()=>{mode=b.dataset.modeTab;render();});render();
  form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;error.textContent='';
    try{
      const data=Object.fromEntries(new FormData(form));data.modo=role==='admin'?'login':mode;
      const result=await D.api('cuenta/','POST',data);
      if(role==='admin'&&!result.usuario.equipo){await D.api('cuenta/','POST',{modo:'logout'});throw Error('Esta cuenta no tiene permisos de administración. Usa la cuenta autorizada por el local.');}
      location.href=role==='admin'?'/equipo/':params.has('producto')?'/?producto='+encodeURIComponent(params.get('producto')):'/';
    }catch(err){error.textContent=err.message;submit.disabled=false;}
  };
}
async function loadOrders(){
  const orders=await D.api('pedidos/');
  document.querySelector('#my-orders').innerHTML=orders.length?orders.map(p=>`<article class="order-card"><div class="order-header"><div><span class="eyebrow">${p.codigo}</span><h3>${D.esc(p.producto)} <span class="muted">× ${p.cantidad}</span></h3></div>${D.badge(p)}</div>${D.progress(p)}<div class="order-meta"><span>Retiro: ${D.date(p.retiro)}</span><span>${p.estado==='COTIZACION'?'Precio base: ':''}${D.money(p.total)}</span><span>${p.pagado?'Pago recibido':'Pago al retirar'}</span></div>${p.nota_equipo?`<div class="notice"><strong>El equipo te cuenta:</strong> ${D.esc(p.nota_equipo)}</div>`:''}${p.diseno||p.preferencias?`<p class="small-text muted">Tu idea: ${D.esc([p.diseno,p.preferencias].filter(Boolean).join(' · '))}</p>`:''}<div class="order-actions">${p.estado==='COTIZADO'?`<button class="button small rose" data-accept="${p.id}">Aceptar cotización · ${D.money(p.total)}</button>`:''}<button class="button small outline" data-detail="${p.id}">Ver seguimiento y QR</button>${!['COTIZACION','COTIZADO','CANCELADO'].includes(p.estado)?`<a class="button small outline" href="/api/pedidos/${p.id}/comprobante/" download>Descargar boleta con QR</a>`:''}${['COTIZACION','COTIZADO','RECIBIDO'].includes(p.estado)?`<button class="text-link" data-cancel="${p.id}">Cancelar pedido</button>`:''}</div></article>`).join(''):'<div class="empty"><h3>Aún no hay dulces por aquí.</h3><p>Tu primer pedido puede ser el comienzo de algo rico.</p><a class="button" href="/#vitrina">Explorar la vitrina →</a></div>';
  document.querySelectorAll('[data-detail]').forEach(b=>b.onclick=()=>{const p=orders.find(x=>x.id===Number(b.dataset.detail));D.modal(`<span class="eyebrow">${p.codigo}</span><h2>${D.esc(p.producto)}</h2>${D.badge(p)}${D.timeline(p)}${!['COTIZACION','COTIZADO','CANCELADO'].includes(p.estado)?`<img class="qr-large" src="/api/pedidos/${p.id}/qr/" alt="QR de retiro del pedido"><p class="small-text muted">Presenta este QR en el mesón. Es personal: no lo compartas.</p>`:'<p class="notice">El QR de retiro se muestra después de confirmar el pedido.</p>'}`);});
  document.querySelectorAll('[data-accept]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await D.api(`pedidos/${b.dataset.accept}/aceptar/`,'POST',{});await loadOrders();D.toast('Cotización aceptada. Tus ingredientes ya están reservados.');}catch(e){D.toast(e.message);b.disabled=false;}});
  document.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=()=>{D.modal('<h2>¿Cancelar este pedido?</h2><p>Se liberarán los ingredientes reservados. Esta acción no puede deshacerse.</p><button class="button danger" id="confirm-cancel">Sí, cancelar pedido</button>');document.querySelector('#confirm-cancel').onclick=async e=>{e.target.disabled=true;try{await D.api(`pedidos/${b.dataset.cancel}/estado/`,'POST',{estado:'CANCELADO'});D.close();await loadOrders();}catch(err){D.toast(err.message);e.target.disabled=false;}};});
}
async function tracking(){
  try{const p=await D.api('seguimiento/'+document.querySelector('.tracking').dataset.token+'/');document.querySelector('#tracking-content').innerHTML=`<span class="eyebrow">${p.codigo}</span><h2>${D.esc(p.producto)} × ${p.cantidad}</h2>${D.badge(p)}${D.progress(p)}<p>Retiro: ${D.date(p.retiro)}</p>${D.timeline(p)}${p.estado==='LISTO'?'<div class="notice">¡Ya está listo! Te esperamos en el mesón.</div>':''}`;}catch(e){document.querySelector('#tracking-content').innerHTML='<p>No encontramos este pedido. Inicia sesión y revísalo en Mis compras.</p>';}
}
