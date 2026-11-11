import {QUOTES} from './quotes.mjs';
const DAY = 86400000;
const options = ['Ja 💪','Workout gemacht (Bild gesendet) 📸','Nein ❌'];
export function localTime(now) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Berlin',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));
  const day = `${p.year}-${p.month}-${p.day}`;
  return {day,hour:Number(p.hour),minute:Number(p.minute),weekday:(new Date(day+'T12:00:00Z').getUTCDay()+6)%7};
}
export function dailyTarget(day) { return day >= '2026-12-01' ? 130 : 125; }
const escape = text => String(text).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const label = day => day.slice(8,10)+'.'+day.slice(5,7)+'.';
export function dateLink(poll,day,chat) {
  const id = poll.chat_id ?? chat;
  if (!Number.isSafeInteger(id) || !String(id).startsWith('-100') || !Number.isSafeInteger(poll.message_id) || poll.message_id<=0) return label(day);
  return `<a href="https://t.me/c/${String(id).slice(4)}/${poll.message_id}">${label(day)}</a>`;
}
export function previousMonday(day) {
  const time = new Date(day+'T12:00:00Z');
  return new Date(+time-(((time.getUTCDay()+6)%7)+7)*DAY).toISOString().slice(0,10);
}
export function weeklyReport(state,monday,chat) {
  const days = Array.from({length:7},(_,i)=>new Date(+new Date(monday+'T12:00:00Z')+i*DAY).toISOString().slice(0,10));
  const polls = Object.fromEntries(Object.values(state.polls).filter(p=>days.includes(p.day)).map(p=>[p.day,p]));
  const title = `📝 Fehlende Abstimmungen ${label(monday)}–${label(days[6])}${days[6].slice(0,4)}`;
  const incomplete = days.filter(d=>!polls[d]?.complete || polls[d].total !== Object.keys(polls[d].votes).length);
  if (incomplete.length) return `${title}\n\nDie Datenerfassung ist unvollständig. Deshalb heute keine Tags wegen fehlender Antworten.\nBetroffene Tage: ${incomplete.map(label).join(', ')}`;
  const missing = Object.entries(state.members).map(([uid,m])=>({uid,m,days:days.filter(d=>m.start<=d&&(!m.end||d<m.end)&&polls[d].votes[uid]===undefined)})).filter(x=>x.days.length).sort((a,b)=>a.m.name.localeCompare(b.m.name));
  const lines = [title,'',missing.length ? 'Für diese Tage fehlt noch eure Antwort:' : 'Alle haben geantwortet – danke euch! 🙌'];
  for (const {uid,m,days:absent} of missing) {
    if (!/^\d+$/.test(uid)) throw new Error('Invalid member ID');
    lines.push(`<a href="tg://user?id=${uid}">${escape(m.name)}</a>: ${absent.map(d=>dateLink(polls[d],d,chat)).join(', ')}`);
  }
  return lines.join('\n');
}
export function chooseQuote(state,day) {
  state.quote_choices ??= {}; state.quote_bag ??= [];
  if (state.quote_choices[day]===undefined) {
    if (!state.quote_bag.length) {
      state.quote_bag = QUOTES.map((_,i)=>i);
      for (let i=state.quote_bag.length-1;i>0;i--) {const j=crypto.getRandomValues(new Uint32Array(1))[0]%(i+1);[state.quote_bag[i],state.quote_bag[j]]=[state.quote_bag[j],state.quote_bag[i]];}
      if (state.quote_bag.at(-1)===state.last_quote) [state.quote_bag[0],state.quote_bag[state.quote_bag.length-1]]=[state.quote_bag.at(-1),state.quote_bag[0]];
    }
    state.quote_choices[day]=state.quote_bag.pop(); state.last_quote=state.quote_choices[day];
  }
  return QUOTES[state.quote_choices[day]].replaceAll('{target}',String(dailyTarget(day)));
}
export function applyUpdate(state,update,chat) {
  const a=update.poll_answer;
  if (a?.user && state.polls[a.poll_id]) {
    const votes=state.polls[a.poll_id].votes, uid=String(a.user.id);
    if (a.option_ids.length) votes[uid]=a.option_ids[0]; else delete votes[uid];
  }
  const p=update.poll;
  if (p && state.polls[p.id]) state.polls[p.id].total=p.total_voter_count;
  const m=update.message;
  if (m?.chat?.id===chat) {
    const day=localTime(new Date(m.date*1000)).day;
    for (const u of m.new_chat_members||[]) if (!u.is_bot) state.members[String(u.id)]={name:[u.first_name,u.last_name].filter(Boolean).join(' '),start:day,end:null};
    if (m.left_chat_member && state.members[String(m.left_chat_member.id)]) state.members[String(m.left_chat_member.id)].end=day;
  }
  state.offset=Math.max(state.offset,update.update_id+1);
}
export async function collect(tg,save,state,now) {
  if (state.collected_at && +now/1000-state.collected_at>23*3600) for (const p of Object.values(state.polls)) if (!p.historical) p.complete=false;
  let drained=false;
  for (let batch=0;batch<20;batch++) {
    const updates=await tg.call('getUpdates',{offset:state.offset,timeout:0,limit:100,allowed_updates:['poll_answer','poll','message']});
    if (!updates.length) {drained=true;break;}
    for (const u of updates) applyUpdate(state,u,tg.chat);
    await save(state); // Never acknowledge an update before its data is durable.
  }
  if (!drained) throw new Error('Update backlog exceeds per-tick limit');
  state.collected_at=+now/1000;
  await save(state);
}
export async function sendOnce(tg,save,state,key,method,payload,onSuccess) {
  if (state.sent[key]!==undefined) {
    if (state.sent[key]==='pending') throw new Error('Ambiguous previous send; inspect Telegram before retrying');
    return;
  }
  state.sent[key]='pending'; await save(state);
  const result=await tg.call(method,{chat_id:tg.chat,...payload});
  state.sent[key]=result.message_id;
  if (onSuccess) onSuccess(result);
  await save(state);
}
export async function preflight(tg) {
  const me=await tg.call('getMe',{}), chat=await tg.call('getChat',{chat_id:tg.chat}), webhook=await tg.call('getWebhookInfo',{});
  if (!me.is_bot || chat.id!==tg.chat || webhook.url) throw new Error('Telegram configuration is not ready for polling');
  return {telegramReady:true};
}
export async function tick(tg,save,state,now=new Date()) {
  await collect(tg,save,state,now);
  const t=localTime(now), day=t.day;
  if (t.weekday>0 || t.hour>=8) {
    const monday=previousMonday(day);
    await sendOnce(tg,save,state,'report:'+monday,'sendMessage',{text:weeklyReport(state,monday,tg.chat),parse_mode:'HTML',link_preview_options:{is_disabled:true}});
  }
  if (t.hour===9) {
    await sendOnce(tg,save,state,'poll:'+day,'sendPoll',{question:`${label(day)} · Hast du heute ${dailyTarget(day)} Liegestütze gemacht?`,options:options.map(text=>({text})),is_anonymous:false,allows_multiple_answers:false},result=>{
      state.polls[result.poll.id]={day,message_id:result.message_id,chat_id:tg.chat,votes:{},total:0,complete:true};
    });
    if ([1,4].includes(t.weekday)) {
      const text=chooseQuote(state,day);await save(state);
      await sendOnce(tg,save,state,'quote:'+day,'sendMessage',{text});
    }
  }
  if (t.hour===21) {
    if (!Number.isSafeInteger(state.sent['poll:'+day])) throw new Error('Today poll missing; reminder suppressed');
    await sendOnce(tg,save,state,'reminder:'+day,'sendMessage',{text:'⏰ Erinnerung: Bitte vergiss nicht abzustimmen!'});
  }
  // A missed delivery is an error, not a silent successful tick.
  if (t.hour>=10&&!Number.isSafeInteger(state.sent['poll:'+day])) throw new Error('Today morning poll was missed');
  const cutoff=new Date(+now-90*DAY).toISOString().slice(0,10);
  for (const [key,p] of Object.entries(state.polls)) if (p.day<cutoff) delete state.polls[key];
  await save(state);
}
