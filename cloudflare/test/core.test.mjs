import test from 'node:test';
import assert from 'node:assert/strict';
import {applyUpdate,chooseQuote,dailyTarget,localTime,previousMonday,tick,weeklyReport,sendOnce,collect} from '../src/core.mjs';
import {encryptState,decryptState,adminToken,authorized} from '../src/crypto.mjs';

const key=Buffer.alloc(32,4).toString('base64url');
function fixture() {return {version:1,offset:0,members:{'1':{name:'A & B',start:'2026-11-01',end:null}},polls:{},sent:{'report:2026-11-02':42}};}
function harness(state=fixture()) {
  const saved=[],messages=[];
  const tg={chat:-1001234567890,async call(method,payload) {
    if(method==='getUpdates') return [];
    messages.push({method,payload});return {message_id:messages.length,poll:{id:'p'+messages.length}};
  }};
  return {state,saved,messages,tg,save:async s=>saved.push(structuredClone(s))};
}

test('09 local and 21 local across winter, summer and DST changes',()=>{
  for(const [utc,day,hour] of [['2026-11-11T08:00:00Z','2026-11-11',9],['2027-07-11T07:00:00Z','2027-07-11',9],['2027-03-28T07:00:00Z','2027-03-28',9],['2027-10-31T08:00:00Z','2027-10-31',9],['2026-11-11T20:00:00Z','2026-11-11',21],['2027-07-11T19:00:00Z','2027-07-11',21]]) {
    assert.deepEqual([localTime(new Date(utc)).day,localTime(new Date(utc)).hour],[day,hour]);
  }
});
test('daily and motivational targets change only at the confirmed date',()=>{
  assert.equal(dailyTarget('2026-11-30'),125);assert.equal(dailyTarget('2026-12-01'),130);assert.equal(dailyTarget('2027-01-01'),130);
});
test('poll sends once at nine, quote twice weekly, reminder once at 21',async()=>{
  const h=harness();
  for(let i=0;i<3;i++) await tick(h.tg,h.save,h.state,new Date('2026-11-10T08:00:00Z'));
  assert.deepEqual(h.messages.map(x=>x.method),['sendPoll','sendMessage']);
  assert.match(h.messages[0].payload.question,/10\.11\. · Hast du heute 125/);
  for(let i=0;i<3;i++) await tick(h.tg,h.save,h.state,new Date('2026-11-10T20:00:00Z'));
  assert.equal(h.messages.length,3);assert.match(h.messages[2].payload.text,/Erinnerung/);
});
test('other weekdays have no motivation line',async()=>{
  const h=harness();await tick(h.tg,h.save,h.state,new Date('2026-11-11T08:00:00Z'));
  assert.deepEqual(h.messages.map(x=>x.method),['sendPoll']);
});
test('no evening catch-up poll; absent poll produces a visible error',async()=>{
  const h=harness();await assert.rejects(tick(h.tg,h.save,h.state,new Date('2026-11-10T15:00:00Z')),/poll was missed/);
  assert.equal(h.messages.length,0);
});
test('no reminder for a nonexistent poll',async()=>{
  const h=harness();await assert.rejects(tick(h.tg,h.save,h.state,new Date('2026-11-10T20:00:00Z')),/reminder suppressed/);
  assert.equal(h.messages.length,0);
});
test('no immediate repeats, all twenty choices, stable retry choice',()=>{
  const state=fixture(), texts=[];
  for(let i=1;i<=20;i++)texts.push(chooseQuote(state,`2026-11-${String(i).padStart(2,'0')}`));
  assert.equal(new Set(texts).size,20);assert.equal(chooseQuote(state,'2026-11-01'),texts[0]);assert.notEqual(chooseQuote(state,'2026-11-21'),texts.at(-1));
});
test('weekly report contains only missing dates with correct permalinks and escaped names',()=>{
  const s=fixture();
  for(let i=2;i<=8;i++)s.polls['x'+i]={day:`2026-11-0${i}`,complete:true,total:i===4?0:1,votes:i===4?{}:{'1':2},message_id:100+i};
  const text=weeklyReport(s,'2026-11-02',-1001234567890);
  assert.match(text,/A &amp; B/);assert.match(text,/https:\/\/t.me\/c\/1234567890\/104/);assert.ok(text.endsWith('04.11.</a>'));assert.ok(!text.includes('Bitte stimmt'));assert.ok(!text.includes('%'));
  s.polls.x4.complete=false;assert.ok(!weeklyReport(s,'2026-11-02',-1001234567890).includes('tg://'));
});
test('Monday boundary calculation',()=>{
  assert.equal(previousMonday('2026-11-09'),'2026-11-02');assert.equal(previousMonday('2026-11-15'),'2026-11-02');assert.equal(previousMonday('2026-11-16'),'2026-11-09');
});
test('vote changes/retractions and offset survive existing schema',()=>{
  const s=fixture();s.polls.p={votes:{},total:0};
  for(const [id,options]of [[1,[0]],[2,[2]],[3,[]]])applyUpdate(s,{update_id:id,poll_answer:{poll_id:'p',user:{id:1},option_ids:options}},-1);
  assert.deepEqual(s.polls.p.votes,{});assert.equal(s.offset,4);
});
test('updates are persisted before Telegram acknowledgement',async()=>{
  const h=harness();h.state.polls.p={votes:{},day:'2026-11-10',complete:true,total:1};let calls=0;
  h.tg.call=async(m,p)=>{if(calls++===0)return[{update_id:9,poll_answer:{poll_id:'p',user:{id:1},option_ids:[0]}}];assert.equal(h.saved.at(-1).offset,p.offset);return[];};
  await collect(h.tg,h.save,h.state,new Date());assert.equal(h.state.polls.p.votes['1'],0);
});
test('ambiguous delivery is not retried or silently duplicated',async()=>{
  const h=harness();let calls=0;h.tg.call=async()=>{calls++;throw new Error('timeout');};
  for(let i=0;i<2;i++)await assert.rejects(sendOnce(h.tg,h.save,h.state,'poll:x','sendPoll',{}));assert.equal(calls,1);assert.equal(h.state.sent['poll:x'],'pending');
});
test('authenticated encryption and admin authentication',async()=>{
  const s=fixture(),cipher=await encryptState(s,key);assert.deepEqual(await decryptState(cipher,key),s);
  await assert.rejects(decryptState(cipher,Buffer.alloc(32,5).toString('base64url')));
  const token=await adminToken(key);assert.equal(await authorized(new Request('https://x',{headers:{authorization:'Bearer '+token}}),key),true);assert.equal(await authorized(new Request('https://x'),key),false);
});

test('imports Python Fernet state without changing offsets, answers or dedup markers',async()=>{
  const {readFile}=await import('node:fs/promises');
  const state=await decryptState(await readFile(new URL('./legacy-state.enc',import.meta.url),'utf8'),key);
  assert.equal(state.offset,12345); assert.equal(state.polls.abc.votes['1'],2);
  assert.equal(state.sent['poll:2026-11-10'],100);assert.equal(state.quote_choices['2026-11-10'],4);
  assert.deepEqual(await decryptState(await encryptState(state,key),key),state);
});

test('preflight only checks configuration and never consumes or sends',async()=>{
  const {preflight}=await import('../src/core.mjs');const methods=[];
  const tg={chat:-1001234567890,async call(m){methods.push(m);return m==='getMe'?{is_bot:true}:m==='getChat'?{id:this.chat}:{url:''};}};
  assert.deepEqual(await preflight(tg),{telegramReady:true});
  assert.deepEqual(methods,['getMe','getChat','getWebhookInfo']);
  await assert.rejects(()=>preflight({...tg,async call(m){return m==='getMe'?{is_bot:true}:m==='getChat'?{id:this.chat}:{url:'https://example.com'};}}));
});

test('large history encrypts without argument-size failures',async()=>{
 const state=fixture();state.test_padding='x'.repeat(300000);
 assert.deepEqual(await decryptState(await encryptState(state,key),key),state);
});
