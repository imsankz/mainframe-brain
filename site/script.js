const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('visible');observer.unobserve(entry.target)}}),{threshold:.12});
document.querySelectorAll('.reveal').forEach(el=>observer.observe(el));
const menu=document.querySelector('.menu');menu.addEventListener('click',()=>{const nav=document.querySelector('.nav');const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open))});
document.querySelectorAll('.nav nav a').forEach(a=>a.addEventListener('click',()=>document.querySelector('.nav').classList.remove('open')));
const copy=document.querySelector('#copy');copy.addEventListener('click',async()=>{const text=document.querySelector('.code-card code').innerText;await navigator.clipboard.writeText(text);copy.textContent='Copied!';setTimeout(()=>copy.textContent='Copy',1600)});
