'use strict';
const $=(query)=>document.querySelector(query);
const $$=(query)=>Array.from(document.querySelectorAll(query));
const safe=(value)=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(cents)=>(Number(cents||0)/100).toLocaleString('en-US',{style:'currency',currency:'USD'});
function alertBox(selector,msg){const el=$(selector);if(el){el.textContent=msg;el.hidden=!msg}}
async function api(path,opts={}){
  const response=await fetch('/api'+path,{credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json',...opts.headers},...opts});
  let data;try{data=await response.json()}catch{throw new Error('Server is not responding correctly')}
  if(!response.ok)throw new Error(data.error||`Server error ${response.status}`);
  return data;
}
function goLogin(){const next=encodeURIComponent(location.pathname+location.search);location.assign('/login?next='+next)}
async function signedIn(required=true){
  try{const {user}=await api('/auth/me');if(!user&&required)goLogin();return user}
  catch(e){if(required)goLogin();return null}
}
function home(){
  $('#copyrightYear').textContent=new Date().getFullYear();
  const beats={3:['Set the opening atmosphere and introduce the main character.','The surprise conflict changes the direction of the story.','Bring everything to an emotional turning point.'],5:['Establish the neighborhood and introduce the lead.','Reveal a message or incident that changes everything.','Raise the stakes through a difficult relationship or choice.','Build toward the most dramatic confrontation.','Close with a memorable consequence or new beginning.'],8:['Establish the atmosphere and the central character.','Show their daily life and what they want.','Introduce the event that changes everything.','Create a serious setback.','Reveal a secret that reframes the story.','Show a difficult meeting or confrontation.','Deliver the climactic decision.','Resolve the story with a strong final image.']};
  $('#demoBuild').addEventListener('click',()=>{
    const plot=$('#demoPrompt').value.trim();if(plot.length<12){alert('Describe your movie in at least 12 characters.');$('#demoPrompt').focus();return}
    const genre=$('#demoGenre').value;const beatsList=beats[Number($('#demoScenes').value)];const result=$('#demoResult');result.hidden=false;result.replaceChildren();
    const h=document.createElement('h4');h.textContent='YOUR DIRECTOR\'S STORYBOARD';result.appendChild(h);
    for(let i=0;i<beatsList.length;i++){
      const div=document.createElement('div');div.className='demo-shot';div.contentEditable='true';
      const title=document.createElement('b');title.textContent=`SCENE ${String(i+1).padStart(2,'0')} / ${genre.toUpperCase()}`;
      const description=document.createElement('span');description.textContent=beatsList[i]+' Story direction: '+plot.slice(0,100)+(plot.length>100?'…':'');
      div.append(title,description);result.appendChild(div);
    }
    const note=document.createElement('p');note.className='mini-note';note.textContent='Tap any scene to edit its text. This storyboard does not create video footage.';result.appendChild(note);
    result.scrollIntoView({behavior:'smooth',block:'nearest'});
  });
}
async function pricing(){
  let plans=[];
  try{const response=await api('/pricing');plans=response.packs||[]}
  catch(e){alertBox('#pricingStatus','Could not load current plans: '+e.message);return}
  let active='payment';
  function draw(){
    const grid=$('#planGrid');grid.textContent='';grid.classList.toggle('memberships',active==='subscription');
    plans.filter(p=>p.kind===active).forEach((plan,i)=>{
      const art=document.createElement('article');art.className='price-card'+((active==='payment'&&i===1)||(active==='subscription'&&i===1)?' popular':'');
      const label=document.createElement('span');label.className='plan-label';label.textContent=(i===1?'MOST POPULAR / ':'')+(active==='payment'?'ONE-TIME CREDITS':'MONTHLY PLAN');
      const name=document.createElement('h3');name.textContent=plan.name;
      const sum=document.createElement('div');sum.className='price-amount';sum.textContent=fmt(plan.cents);
      const credits=document.createElement('p');credits.className='credits';credits.textContent=plan.credits+' credits '+(active==='subscription'?'/ month':'to use when ready');
      const detail=document.createElement('p');detail.className='details';detail.textContent=active==='payment'?'One-time purchase. Credits used when you create AI video.':'Recurring subscription. Monthly credits are granted after confirmed payment.';
      const button=document.createElement('button');button.className='btn btn-primary';button.type='button';button.textContent=plan.available?'Choose '+plan.name:'Checkout not live yet';button.disabled=!plan.available;
      button.addEventListener('click',async()=>{
        if(!await signedIn())return;
        button.disabled=true;button.textContent='Opening secure checkout…';
        try{const {url}=await api('/billing/checkout',{method:'POST',body:JSON.stringify({sku:plan.sku})});location.assign(url)}
        catch(e){alertBox('#pricingStatus',e.message);button.disabled=false;button.textContent='Choose '+plan.name}
      });
      art.append(label,name,sum,credits,detail,button);grid.appendChild(art);
    });
  }
  $$('.pricing-switch button').forEach(b=>b.addEventListener('click',()=>{active=b.dataset.plan;$$('.pricing-switch button').forEach(x=>x.classList.toggle('selected',x===b));draw()}));
  draw();
}
function login(){
  let mode='login';const target=new URLSearchParams(location.search).get('next')||'/dashboard';
  function render(){
    $$('[data-auth-tab]').forEach(b=>b.classList.toggle('selected',b.dataset.authTab===mode));
    $('#nameField').hidden=mode!=='register';$('#ownerField').hidden=mode!=='register';$('#authName').required=mode==='register';
    $('#authHeading').textContent=mode==='login'?'Welcome back.':'Create your account.';
    $('#authSubtitle').textContent=mode==='login'?'Sign in to keep creating.':'Join One Hit Wonder and build your first movie.';
    $('#authSubmit').textContent=mode==='login'?'Sign in ↗':'Create account ↗';
    $('#authPassword').autocomplete=mode==='login'?'current-password':'new-password';alertBox('#authError','');
  }
  $$('[data-auth-tab]').forEach(b=>b.addEventListener('click',()=>{mode=b.dataset.authTab;render()}));render();
  $('#authForm').addEventListener('submit',async e=>{
    e.preventDefault();const btn=$('#authSubmit');btn.disabled=true;alertBox('#authError','');
    const payload={email:$('#authEmail').value,password:$('#authPassword').value};
    if(mode==='register'){payload.name=$('#authName').value;payload.owner_code=$('#ownerCode').value.trim()}
    try{await api('/auth/'+(mode==='register'?'register':'login'),{method:'POST',body:JSON.stringify(payload)});
      location.assign(target.startsWith('/')&&!target.startsWith('//')?target:'/dashboard')}
    catch(err){alertBox('#authError',err.message);btn.disabled=false}
  });
}
async function dashboard(){
  const user=await signedIn();if(!user)return;
  $('#welcomeText').textContent=`Welcome back, ${user.name}. Keep making stories worth watching.`;
  $('#creditsValue').textContent=user.role==='owner'?'∞':user.credits.toLocaleString();
  $('#creditsHint').textContent=user.role==='owner'?'Unlimited in-app credit access':'Available to render';
  $('#planValue').textContent=user.role==='owner'?'OWNER':user.plan.toUpperCase();
  if(user.role==='owner')$('#adminNav').hidden=false;
  try{
    const [account,jobs]=await Promise.all([api('/account/summary'),api('/jobs')]);
    $('#videoCount').textContent=jobs.jobs.length;
    const history=$('#recentProjects');history.textContent='';
    if(!jobs.jobs.length)history.innerHTML='<p>No videos yet. Your first one could be iconic.</p>';
    jobs.jobs.slice(0,6).forEach(j=>{
      const row=document.createElement('div');row.className='activity-row';
      const col=document.createElement('div');const name=document.createElement('b');name.textContent=j.title||j.prompt||'Video project';const status=document.createElement('span');status.textContent=j.status+' · '+j.duration+'s';col.append(name,status);
      const action=document.createElement('a');action.href=j.status==='completed'?j.video_url+'?download=1':'/studio';action.textContent=j.status==='completed'?'Download ↓':'View →';row.append(col,action);history.appendChild(row);
    });
    const activity=$('#creditActivity');activity.textContent='';
    if(!account.ledger?.length)activity.innerHTML='<p>No credit transactions yet.</p>';
    (account.ledger||[]).slice(0,8).forEach(x=>{const row=document.createElement('div');row.className='activity-row';const desc=document.createElement('span');desc.textContent=x.reason;const amount=document.createElement('b');amount.textContent=(x.amount>0?'+':'')+x.amount;amount.className=x.amount>=0?'positive':'negative';row.append(desc,amount);activity.appendChild(row)});
  }catch(e){alertBox('#dashError',e.message)}
}
async function admin(){
  const user=await signedIn();if(!user)return;
  if(user.role!=='owner'){location.assign('/dashboard');return}
  async function refresh(){
    try{
      const [stats,list]=await Promise.all([api('/admin/stats'),api('/admin/users')]);
      $('#adminUsers').textContent=stats.users.toLocaleString();$('#adminRevenue').textContent=fmt(stats.revenue_cents);
      $('#adminGenerations').textContent=stats.generations.toLocaleString();$('#adminCosts').textContent='$'+stats.estimated_provider_usd.toFixed(2);
      const holder=$('#userTable');holder.textContent='';
      const header=document.createElement('div');header.className='user-header';['MEMBER','ROLE','CREDITS','GRANT BONUS CREDITS'].forEach(t=>{const s=document.createElement('span');s.textContent=t;header.appendChild(s)});holder.appendChild(header);
      list.users.forEach(u=>{
        const row=document.createElement('div');row.className='user-row';
        const identity=document.createElement('div');const name=document.createElement('b');name.textContent=u.name;const email=document.createElement('small');email.textContent=u.email;identity.append(name,email);
        const role=document.createElement('span');role.textContent=u.role.toUpperCase();
        const credits=document.createElement('span');credits.textContent=u.role==='owner'?'∞':u.credits;
        const form=document.createElement('form');form.className='grant-row';const input=document.createElement('input');input.type='number';input.min=1;input.max=1000;input.value=10;input.setAttribute('aria-label','Credits to grant');
        const btn=document.createElement('button');btn.textContent='Grant';btn.disabled=u.role==='owner';
        form.append(input,btn);form.addEventListener('submit',async e=>{e.preventDefault();btn.disabled=true;try{await api('/admin/grant',{method:'POST',body:JSON.stringify({user_id:u.id,amount:Number(input.value)})});await refresh()}catch(err){alertBox('#adminError',err.message);btn.disabled=false}});
        row.append(identity,role,credits,form);holder.appendChild(row);
      });
    }catch(e){alertBox('#adminError',e.message)}
  }
  $('#refreshAdmin').addEventListener('click',refresh);await refresh();
}
const logout=$('#logoutButton');if(logout)logout.addEventListener('click',async()=>{try{await api('/auth/logout',{method:'POST',body:'{}'})}catch{}location.assign('/')});
const page=document.body.dataset.page;
if(page==='home')home();if(page==='pricing')pricing();if(page==='login')login();if(page==='dashboard')dashboard();if(page==='admin')admin();
