const toggle = document.querySelector('#care-toggle');
const menu = document.querySelector('#care-menu');
const dialog = document.querySelector('#service-dialog');
let services = [];
const divisionPages = {'transitional-care':'/transitional-care.html','hospital-medicine':'/hospital-medicine.html'};
function closeMenu() { menu.hidden = true; toggle.setAttribute('aria-expanded', 'false'); }
toggle.addEventListener('click', () => { const open = menu.hidden; menu.hidden = !open; toggle.setAttribute('aria-expanded', String(open)); });
document.addEventListener('click', event => { if (!menu.contains(event.target) && !toggle.contains(event.target)) closeMenu(); });
document.addEventListener('keydown', event => { if(event.key === 'Escape' && !menu.hidden) { closeMenu(); toggle.focus(); } });
function showService(id) {
 if(Object.hasOwn(divisionPages,id)) { location.href = divisionPages[id]; return; }
 const service = services.find(item => item.id === id);
 if (!service) return;
 closeMenu();
 for (const field of ['status','title','caption','description','note']) document.querySelector('#service-' + field).textContent = service[field === 'title' ? 'name' : field];
 document.querySelector('#service-points').replaceChildren(...service.points.map(point => { const li = document.createElement('li'); li.textContent = point; return li; }));
 const action = document.querySelector('#service-action');
 action.hidden = !service.interest;
 action.href = '/care-access.html?service=' + encodeURIComponent(service.interest || '');
 if(!dialog.open) dialog.showModal();
}
document.addEventListener('click', event => { const link = event.target.closest('[data-service]'); if(link) { event.preventDefault(); showService(link.dataset.service); } });
dialog.querySelector('.close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if(event.target === dialog) { const rect = dialog.getBoundingClientRect(); if(event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });
fetch('/care-services.json').then(response => { if(!response.ok) throw new Error('Unavailable'); return response.json(); }).then(data => {
 services = data.services;
 document.querySelector('#care-links').replaceChildren(...services.map(service => { const link = document.createElement('a'); link.href = divisionPages[service.id] || '#' + service.id; if(!divisionPages[service.id]) link.dataset.service = service.id; link.append(document.createTextNode(service.name)); const status = document.createElement('small'); status.textContent = service.status; link.append(status); return link; }));
 showService(location.hash.slice(1));
}).catch(() => { document.querySelector('#care-links').textContent = 'Care details are temporarily unavailable. Please try again later.'; document.querySelectorAll('[data-service]').forEach(link => { if(link.tagName === 'A') { link.removeAttribute('data-service'); link.href = '/care-access.html'; } else { link.disabled = true; } }); });

// Practice information is independent of the patient-service catalog.
const practices = document.querySelector('#practices-dialog');
document.querySelector('#practices-toggle').addEventListener('click', () => {
 closeMenu();
 practices.showModal();
});
practices.querySelector('.close').addEventListener('click', () => practices.close());
document.querySelector('#practices-purpose').addEventListener('click', () => { practices.close(); document.querySelector('#about').open = true; });
practices.addEventListener('click', event => {
 if(event.target !== practices) return;
 const rect = practices.getBoundingClientRect();
 if(event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) practices.close();
});
