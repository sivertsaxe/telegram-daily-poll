import {spawnSync} from 'node:child_process';
const secrets=Object.fromEntries(['STATE_KEY','TG_TOKEN','TG_CHAT_ID'].map(name=>{
 if(!process.env[name]) throw new Error('Missing required bot secret');
 return [name,process.env[name]];
}));
const result=spawnSync('npx',['--no-install','wrangler','secret','bulk'],{input:JSON.stringify(secrets),stdio:['pipe','inherit','inherit']});
process.exit(result.status??1);
