import {DurableObject} from 'cloudflare:workers';
import {authorized,decryptState,encryptState} from './crypto.mjs';
import {preflight,tick} from './core.mjs';

class Telegram {
  constructor(env) {this.token=env.TG_TOKEN;this.chat=Number(env.TG_CHAT_ID);}
  async call(method,payload) {
    let response,body;
    try {
      response=await fetch(`https://api.telegram.org/bot${this.token}/${method}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(20000)});
      body=await response.json();
    } catch {throw new Error(`Telegram ${method} connection failure`);}
    if (!response.ok||!body.ok) throw new Error(`Telegram ${method} API error ${body.error_code||response.status}`);
    return body.result;
  }
}
export class ChallengeBot extends DurableObject {
  constructor(ctx,env) {super(ctx,env);this.env=env;this.queue=Promise.resolve();}
  async fetch(request) {
    const operation=this.queue.then(()=>this.handle(request));
    this.queue=operation.catch(()=>{});
    try{return await operation;}catch {return Response.json({ok:false,error:'Operation failed; inspect private worker status'},{status:500});}
  }
  async handle(request) {
    const path=new URL(request.url).pathname;
    if (path==='/health') return Response.json({ready:Boolean(await this.ctx.storage.get('ciphertext')),active:Boolean(await this.ctx.storage.get('active')),lastTick:await this.ctx.storage.get('lastTick')||null,status:await this.ctx.storage.get('status')||'not initialized'});
    if (path.startsWith('/admin/') && !await authorized(request,this.env.STATE_KEY)) return new Response('Unauthorized',{status:401});
    const tg=new Telegram(this.env);
    const save=async state=>this.ctx.storage.put('ciphertext',await encryptState(state,this.env.STATE_KEY));
    if (path==='/admin/import' && request.method==='POST') {
      if (await this.ctx.storage.get('active')) return new Response('Deactivate before importing',{status:409});
      const state=await decryptState(await request.text(),this.env.STATE_KEY);
      await save(state);await this.ctx.storage.put('status','imported');
      return Response.json({imported:true});
    }
    if (path==='/admin/export' && request.method==='POST') {
      const value=await this.ctx.storage.get('ciphertext');
      if (!value) return new Response('State missing',{status:404});
      return new Response(value,{headers:{'content-type':'text/plain','cache-control':'no-store'}});
    }
    if (path==='/admin/check' && request.method==='POST') {
      const value=await this.ctx.storage.get('ciphertext');
      if (!value) throw new Error('State missing');
      await decryptState(value,this.env.STATE_KEY);
      return Response.json(await preflight(tg));
    }
    if (path==='/admin/activate' && request.method==='POST') {
      const body=await request.json();
      if (body.previous_scheduler_stopped!==true) return new Response('Confirm previous scheduler is stopped',{status:409});
      await preflight(tg);
      if (!await this.ctx.storage.get('ciphertext')) throw new Error('State missing');
      await this.ctx.storage.put('active',true);await this.ctx.storage.put('status','active');
      return Response.json({active:true});
    }
    if (path==='/admin/deactivate' && request.method==='POST') {
      await this.ctx.storage.put('active',false);return Response.json({active:false});
    }
    if (path==='/tick' && request.method==='POST') {
      if (!await this.ctx.storage.get('active')) return Response.json({skipped:'inactive'});
      const state=await decryptState(await this.ctx.storage.get('ciphertext'),this.env.STATE_KEY);
      try {
        await tick(tg,save,state,new Date());
        await this.ctx.storage.put({lastTick:new Date().toISOString(),status:'ok'});
        return Response.json({ok:true});
      } catch (error) {
        // Core errors contain method names only, never request URLs or tokens.
        await this.ctx.storage.put({lastTick:new Date().toISOString(),status:String(error.message).slice(0,160)});
        throw error;
      }
    }
    return new Response('Not found',{status:404});
  }
}
function object(env) {return env.CHALLENGE.get(env.CHALLENGE.idFromName('daily-challenge'));}
export default {
  async fetch(request,env) {
    const path=new URL(request.url).pathname;
    if (path!=='/health' && !path.startsWith('/admin/')) return new Response('Not found',{status:404});
    return object(env).fetch(request);
  },
  async scheduled(controller,env,ctx) {
    const response=await object(env).fetch('https://internal/tick',{method:'POST'});
    if (!response.ok) throw new Error('Challenge tick failed; inspect authenticated status');
  }
};
