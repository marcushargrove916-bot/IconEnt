'use strict';
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const API = '/api';
const state = {config:null,ratio:'9:16',mode:'clip',photos:[],selectedPhotos:new Set(),currentJob:null,polling:null,view:'studio',toastTimer:null};
const fmtMoney = (n) => new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);
const esc = (s) => String(s??'').replace(/[&<>"']/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(message) {
  const el=$('#toast');el.textContent=message;el.hidden=false;
  clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>el.hidden=true,5500);
}
async function api(url,options={}){
  const r=await fetch(`${API}${url}`,{headers:{'Content-Type':'application/json'},cache:'no-store',...options});
  let data;try{data=await r.json()}catch{throw new Error('Could not read the video studio response.')}
  if(!r.ok)throw new Error(data.error||`Server error ${r.status}`);
  return data;
}
function updatePromptCounter(){const p=$('#prompt');$('#charCounter').textContent=`${p.value.length.toLocaleString()} / 2,500`}
function estimate(){
  const seconds=Number($('#duration').value),quality=$('#quality').value;
  const n=state.mode==='movie'?Number($('#sceneCount').value):1;
  const rates=state.config?.rates||{'360p':.03,'720p':.10,'1080p':.15,'4k':.30};
  $('#costEstimate').textContent=fmtMoney(seconds*n*rates[quality]);
  $('#costLabel').textContent=state.mode==='movie'?`Estimated cost for ${n} scenes · ${seconds*n}s total`:'Estimated generation cost';
}
function switchView(name){
  state.view=name;$('#studioView').hidden=name!=='studio';$('#libraryView').hidden=name!=='library';
  $('#pageLabel').textContent=name==='studio'?'Create':'My creations';
  $$('.nav-link').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
  if(name==='library')loadLibrary();window.scrollTo({top:0,behavior:'smooth'});
}
function changeRatio(ratio){
  state.ratio=ratio;
  $$('.ratio-choice').forEach(b=>{b.classList.toggle('selected',b.dataset.ratio===ratio);b.setAttribute('aria-pressed',b.dataset.ratio===ratio?'true':'false')});
}
function switchMode(mode){
  state.mode=mode;
  $$('.mode-choice').forEach(b=>{b.classList.toggle('selected',b.dataset.mode===mode);b.setAttribute('aria-pressed',b.dataset.mode===mode?'true':'false')});
  $('#movieOptions').hidden=mode!=='movie';
  $('#promptLabel').textContent=mode==='movie'?'THE MOVIE PLOT':'DESCRIBE YOUR VIDEO';
  $('#prompt').placeholder=mode==='movie'?'A young musician tries to escape a dangerous neighborhood rivalry, but loyalty to his best friend and a complicated romance bring him back for one final choice…':'A cinematic scene in the Sacramento neighborhood at night, realistic actors, dramatic camera motion, powerful dialogue and ambient sound…';
  $('#generateBtnText').textContent=mode==='movie'?'Generate my movie':'Generate my video';
  if(mode==='movie'){changeRatio('16:9');if($('#quality').value==='4k')$('#quality').value='1080p'}
  estimate();
}
function setBadge(label,kind=''){const b=$('#previewBadge');b.innerHTML=`<span></span>${esc(label)}`;b.className='preview-status'+(kind?' '+kind:'')}
function preview(which){$('#emptyPreview').hidden=which!=='empty';$('#renderingPreview').hidden=which!=='rendering';$('#readyPreview').hidden=which!=='ready'}
function setBusy(value){$('#generateBtn').disabled=value;$('#generateBtnText').textContent=value?'Creating your '+(state.mode==='movie'?'movie…':'video…'):(state.mode==='movie'?'Generate my movie':'Generate my video')}
function showJob(job){
  state.currentJob=job;$('#errorMessage').hidden=true;$('#downloadBtn').hidden=true;
  const kind=job.kind==='movie'?'movie':'video';
  const details=`${job.duration}s total · ${job.resolution} · ${job.aspect_ratio}${job.kind==='movie'?' · '+job.scene_count+' scenes':''}`;
  if(job.status==='completed'){
    setBusy(false);setBadge('READY','done');preview('ready');
    const video=$('#resultVideo');if(video.getAttribute('src')!==job.video_url){video.src=job.video_url;video.load()}
    $('#resultTitle').textContent=job.title||'Your masterpiece is ready';$('#resultSub').textContent=details;
    $('#downloadBtn').href=`${job.video_url}?download=1`;$('#downloadBtn').hidden=false;$('#renderStatus').textContent='Complete';endPolling();
  }else if(job.status==='failed'){
    setBusy(false);setBadge('RENDER FAILED');preview('empty');
    $('#resultTitle').textContent='Some scenes need another take';$('#resultSub').textContent=details;
    const partial=job.completed_scenes?.length?` ${job.completed_scenes.length} completed scenes are still in My creations.`:'';
    $('#errorMessage').textContent=(job.error||'The video service could not complete the render.')+partial;
    $('#errorMessage').hidden=false;endPolling();
  }else{
    setBusy(true);preview('rendering');setBadge('DIRECTING','busy');
    $('#renderStatus').textContent=job.progress||`Creating your ${kind}…`;
    $('#resultTitle').textContent=job.title||'Your vision is taking shape';$('#resultSub').textContent=details;
  }
}
function endPolling(){if(state.polling){clearInterval(state.polling);state.polling=null}}
function startPolling(id){
  endPolling();let fetching=false;
  state.polling=setInterval(async()=>{
    if(fetching)return;fetching=true;
    try{const {job}=await api(`/jobs/${id}`);if(job&&state.currentJob?.id===id){
      const prior=state.currentJob.status;showJob(job);
      if(prior!=='completed'&&job.status==='completed'){toast('🎬 Your movie is ready!');loadLibrary()}
    }}catch(e){console.warn('Retrying render status',e)}finally{fetching=false}
  },5000);
}
async function convertPhoto(file){
  if(file.size>16*1024*1024)throw new Error(`${file.name}: photo is too large to process on your phone.`);
  const url=URL.createObjectURL(file);
  let bitmap;
  try{
    if('createImageBitmap' in window){bitmap=await createImageBitmap(file)}
    else{bitmap=await new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('Unable to open this photo'));img.src=url})}
    const max=1400, w=bitmap.width||bitmap.naturalWidth, h=bitmap.height||bitmap.naturalHeight;
    const scale=Math.min(1,max/Math.max(w,h));
    const canvas=document.createElement('canvas');canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale);
    if(!canvas.width||!canvas.height)throw new Error('Invalid image size');
    const ctx=canvas.getContext('2d');ctx.fillStyle='#141116';ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
    let q=.86,blob;
    for(let i=0;i<4;i++){
      blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',q));
      if(blob&&blob.size<3*1024*1024)break;
      q-=.16;
    }
    if(!blob||blob.size>=3*1024*1024)throw new Error('Try a smaller image.');
    return blob;
  }finally{URL.revokeObjectURL(url);if(bitmap?.close)bitmap.close()}
}
function selectedPhotoIds(){return [...state.selectedPhotos]}
function drawPhotos(){
  const grid=$('#photoGrid');grid.innerHTML='';
  if(!state.photos.length){grid.innerHTML='<div class="cast-empty">Your cast will appear here. Upload photos or create fictional people from your story.</div>';return}
  for(const photo of state.photos){
    const card=document.createElement('div');card.className='cast-photo'+(state.selectedPhotos.has(photo.id)?' selected':'');
    const image=document.createElement('img');image.src=photo.url;image.alt=photo.label;image.loading='lazy';card.appendChild(image);
    const label=document.createElement('span');label.className='cast-name';label.textContent=photo.label;card.appendChild(label);
    const button=document.createElement('button');button.className='cast-select';button.type='button';button.textContent=state.selectedPhotos.has(photo.id)?'✓ In cast':'＋ Add to cast';
    button.addEventListener('click',()=>{if(state.selectedPhotos.has(photo.id))state.selectedPhotos.delete(photo.id);else if(state.selectedPhotos.size<3)state.selectedPhotos.add(photo.id);else{toast('You can use up to three photos in one scene.');return}drawPhotos()});card.appendChild(button);
    const remove=document.createElement('button');remove.className='delete-photo';remove.type='button';remove.title='Delete photo from server';remove.textContent='×';
    remove.addEventListener('click',async()=>{if(!confirm(`Remove ${photo.label} from the server?`))return;try{await api(`/photos/${photo.id}`,{method:'DELETE'});state.selectedPhotos.delete(photo.id);await loadPhotos();toast('Photo removed.')}catch(e){toast(e.message)}});card.appendChild(remove);
    grid.appendChild(card);
  }
}
async function loadPhotos(){
  const {photos}=await api('/photos');state.photos=photos;
  const valid=new Set(photos.map(p=>p.id));for(const id of state.selectedPhotos)if(!valid.has(id))state.selectedPhotos.delete(id);
  drawPhotos();
}
async function onPhotoUpload(event){
  const files=[...event.target.files];event.target.value='';
  if(!files.length)return;
  if(!$('#photoConsent').checked){toast('First confirm you have permission to use the photos.');$('#photoConsent').focus();return}
  for(const file of files.slice(0,6)){
    try{
      toast(`Preparing ${file.name}…`);
      const blob=await convertPhoto(file);
      const r=await fetch(`${API}/photos`,{method:'POST',headers:{'Content-Type':'image/jpeg','X-Photo-Name':encodeURIComponent(file.name),'X-Photo-Consent':'yes'},body:blob});
      const payload=await r.json();if(!r.ok)throw new Error(payload.error||'Upload failed');
      if(state.selectedPhotos.size<3)state.selectedPhotos.add(payload.photo.id);
      await loadPhotos();toast(`${file.name} added to your cast.`);
    }catch(err){toast(err.message)}
  }
  if(files.length>6)toast('Upload up to six photos at a time.');
}
const beats={
  3:['Opening — establish the neighborhood, introduce the main character and immediate stakes.',
     'Conflict — an unexpected confrontation forces a difficult choice.',
     'Payoff — an emotionally powerful turning point with a cinematic final image.'],
  5:['Opening — establish the neighborhood and introduce the lead in everyday life.',
     'Inciting incident — an unexpected message, betrayal or discovery changes everything.',
     'Rising tension — an alliance or relationship is tested in a dramatic conversation.',
     'Climax — the characters face a high-stakes showdown and make a defining choice.',
     'Ending — reveal the consequences and close on a memorable dramatic image.'],
  8:['Opening — atmospheric neighborhood establishing shot and lead introduction.',
     'Everyday stakes — reveal what the main character wants most.',
     'Inciting incident — an unexpected choice threatens the lead’s plans.',
     'First setback — friendship, family or love creates pressure.',
     'Secret revealed — a new twist changes the power balance.',
     'Confrontation — a tense exchange raises the stakes.',
     'Climax — make the hardest choice in a cinematic turning point.',
     'Resolution — characters face the outcome, with a striking closing image.']
};
function buildStoryboard(){
  const plot=$('#prompt').value.trim();if(plot.length<10){toast('Write your story first so the scenes connect.');$('#prompt').focus();return}
  const genre=$('#movieGenre').value,tone=$('#movieTone').value,n=Number($('#sceneCount').value);
  const holder=$('#storyboard');holder.innerHTML='';
  beats[n].forEach((beat,i)=>{
    const section=document.createElement('div');section.className='shot-card';
    const label=document.createElement('label');label.textContent=`SCENE ${String(i+1).padStart(2,'0')} / ${String(n).padStart(2,'0')}`;
    const field=document.createElement('textarea');field.className='shot-prompt';field.maxLength=500;field.rows=3;
    field.value=`${beat} A grounded ${genre.toLowerCase()} moment with a ${tone.toLowerCase()} visual look. Keep it consistent with the plot and characters.`;
    label.appendChild(field);section.appendChild(label);holder.appendChild(section);
  });
  toast('Storyboard ready. Edit any scene to direct your film.');
}
async function generate(){
  const prompt=$('#prompt').value.trim();
  if(prompt.length<(state.mode==='movie'?10:6)){toast('Write your scene or movie plot first.');$('#prompt').focus();return}
  if(!state.config?.ready){toast('To generate footage, add your fal.ai API key in Render. The storyboard and photo tools work now.');$('#setupBanner').hidden=false;$('#setupBanner').scrollIntoView({behavior:'smooth',block:'center'});return}
  if(state.currentJob&&['queued','working','saving'].includes(state.currentJob.status)){toast('Your current production is still rendering.');return}
  const photoIds=selectedPhotoIds();
  if(photoIds.length&&!$('#photoConsent').checked){toast('Please confirm permission to use your cast photos.');return}
  const common={aspect_ratio:state.ratio,resolution:$('#quality').value,duration:Number($('#duration').value),photo_ids:photoIds,photo_consent:!!$('#photoConsent').checked};
  let path='/jobs',payload={...common,prompt};
  if(state.mode==='movie'){
    const scenes=$$('.shot-prompt').map(field=>field.value.trim());
    if(scenes.length!==Number($('#sceneCount').value)){toast('Tap Build storyboard first.');return}
    if(scenes.some(s=>s.length<8)){toast('Fill in every scene before rendering.');return}
    if(!$('#movieTitle').value.trim()){toast('Add your movie title.');$('#movieTitle').focus();return}
    if(!$('#confirmMovieCost').checked){toast('Confirm the multi-scene rendering charges.');return}
    if(payload.resolution==='4k'){toast('For movies choose 1080p or lower.');return}
    path='/movies';payload={...common,title:$('#movieTitle').value.trim(),plot:prompt,genre:$('#movieGenre').value,tone:$('#movieTone').value,scenes,acknowledge_cost:true};
  }
  $('#errorMessage').hidden=true;setBusy(true);preview('rendering');setBadge('STARTING','busy');
  $('#renderStatus').textContent='Creating your production…';
  try{
    const {job}=await api(path,{method:'POST',body:JSON.stringify(payload)});showJob(job);startPolling(job.id);
    toast(state.mode==='movie'?'🎬 Scene-by-scene movie production started!':'Your AI video is rendering!');
  }catch(err){setBusy(false);preview('empty');setBadge('READY');$('#errorMessage').textContent=err.message;$('#errorMessage').hidden=false;toast(err.message)}
}
function formatDate(date){try{return new Date(date).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}catch{return ''}}
async function loadLibrary(){
  try{
    const {jobs}=await api('/jobs');$('#libraryCount').textContent=jobs.filter(j=>j.status==='completed').length;
    const grid=$('#libraryGrid');grid.textContent='';$('#libraryEmpty').hidden=jobs.length!==0;
    jobs.forEach(job=>{
      const card=document.createElement('article');card.className='library-card';
      const done=job.status==='completed';const label=done?'READY':job.status==='failed'?'FAILED':'RENDERING';
      const thumb=done?`<video src="${esc(job.video_url)}" playsinline preload="metadata" controls></video>`:`<span class="placeholder-symbol">${job.kind==='movie'?'▣':'✦'}</span>`;
      const title=job.title||job.prompt;
      const scenes=(job.completed_scenes||[]).map((url,i)=>`<a href="${esc(url)}?download=1" download>Scene ${i+1} ↓</a>`).join(' · ');
      card.innerHTML=`<div class="library-thumb">${thumb}<span class="thumb-state">${label}${job.kind==='movie'?' · MOVIE':''}</span></div><div class="library-card-body"><p title="${esc(title)}">${esc(title)}</p><div class="library-meta"><span>${esc(formatDate(job.created_at))} · ${esc(job.duration)}s</span>${done?`<a href="${esc(job.video_url)}?download=1" download>↓ Save movie</a>`:`<span>${esc(job.resolution)}</span>`}</div>${scenes?`<div class="scene-links">${scenes}</div>`:''}</div>`;
      grid.appendChild(card);
    });
  }catch(e){toast(e.message)}
}
async function init(){
  $$('.nav-link').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.view)));
  $('#emptyCreate').addEventListener('click',()=>switchView('studio'));
  $('#libraryRefresh').addEventListener('click',loadLibrary);
  $$('.ratio-choice').forEach(b=>b.addEventListener('click',()=>changeRatio(b.dataset.ratio)));
  $$('.mode-choice').forEach(b=>b.addEventListener('click',()=>switchMode(b.dataset.mode)));
  $$('#promptChips .chip').forEach(b=>b.addEventListener('click',()=>{$('#prompt').value=b.dataset.prompt;updatePromptCounter();toast('Story idea loaded — make it your own.')}));
  $('#prompt').addEventListener('input',updatePromptCounter);
  $('#duration').addEventListener('change',estimate);$('#quality').addEventListener('change',estimate);
  $('#sceneCount').addEventListener('change',()=>{estimate();$('#storyboard').innerHTML='<div class="storyboard-empty">Scene count changed. Tap Build storyboard to rebuild the shot list.</div>'});
  $('#buildStoryboard').addEventListener('click',buildStoryboard);
  $('#photoUpload').addEventListener('change',onPhotoUpload);
  $('#generateBtn').addEventListener('click',generate);
  updatePromptCounter();estimate();
  try{
    const config=await api('/config');state.config=config;estimate();
    if(config.business_mode){
      try{
        const auth=await api('/auth/me');
        if(!auth.user){location.replace('/login?next=/studio');return}
        $('#accountCredits').textContent=auth.user.role==='owner'?'✦ OWNER / ∞ CREDITS':`✦ ${auth.user.credits} CREDITS`;
        if(auth.user.role==='owner')$('#studioOwnerLink').hidden=false;
      }catch(err){location.replace('/login?next=/studio');return}
    }
    $('#connectionDot').classList.add(config.ready?'online':'offline');
    $('#connectionText').textContent=config.ready?'AI movie engine connected':'API key setup needed';
    $('#setupBanner').hidden=!!config.ready;
  }catch(e){$('#connectionText').textContent='Server unavailable';toast(e.message)}
  try{await loadPhotos()}catch(e){toast('Could not load cast photos: '+e.message)}
  try{
    const {jobs}=await api('/jobs');$('#libraryCount').textContent=jobs.filter(j=>j.status==='completed').length;
    const job=jobs.find(j=>['queued','working','saving'].includes(j.status));
    if(job){showJob(job);startPolling(job.id)}else if(jobs[0]?.status==='completed')showJob(jobs[0]);
  }catch(e){console.warn('Unable to load history',e)}
}
init();
