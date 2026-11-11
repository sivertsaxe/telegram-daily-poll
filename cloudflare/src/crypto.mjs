const enc = new TextEncoder();
export function unbase64(value) {
  return Uint8Array.from(atob(value.trim().replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
}
export function base64(bytes) {
  let binary='';
  for(let i=0;i<bytes.length;i+=8192) binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
  return btoa(binary);
}
export async function encryptState(state, secret) {
  const key = await crypto.subtle.importKey('raw', unbase64(secret), 'AES-GCM', false, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const body = new Uint8Array(await crypto.subtle.encrypt({name: 'AES-GCM', iv, additionalData: enc.encode('challenge-state-v1')}, key, enc.encode(JSON.stringify(state))));
  return 'gcm1.' + base64(iv) + '.' + base64(body);
}
export async function decryptState(value, secret) {
  const rawKey = unbase64(secret);
  let plain;
  if (value.startsWith('gcm1.')) {
    const [,iv,body] = value.split('.');
    const key = await crypto.subtle.importKey('raw', rawKey, 'AES-GCM', false, ['decrypt']);
    plain = await crypto.subtle.decrypt({name:'AES-GCM',iv:unbase64(iv),additionalData:enc.encode('challenge-state-v1')},key,unbase64(body));
  } else {
    // Import the existing Python Fernet ciphertext without resetting vote offsets.
    const bytes = unbase64(value);
    if (bytes[0] !== 128 || bytes.length < 73) throw new Error('Invalid migration ciphertext');
    const signed = bytes.slice(0,-32), mac = bytes.slice(-32);
    const signing = await crypto.subtle.importKey('raw',rawKey.slice(0,16),{name:'HMAC',hash:'SHA-256'},false,['verify']);
    if (!await crypto.subtle.verify('HMAC',signing,mac,signed)) throw new Error('Invalid migration signature');
    const key = await crypto.subtle.importKey('raw',rawKey.slice(16),'AES-CBC',false,['decrypt']);
    plain = await crypto.subtle.decrypt({name:'AES-CBC',iv:bytes.slice(9,25)},key,bytes.slice(25,-32));
  }
  const state = JSON.parse(new TextDecoder().decode(plain));
  if (state.version !== 1 || !state.members || !state.polls || !state.sent || !Number.isInteger(state.offset)) throw new Error('Invalid state schema');
  return state;
}
export async function adminToken(secret) {
  const key = await crypto.subtle.importKey('raw',unbase64(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  return base64(new Uint8Array(await crypto.subtle.sign('HMAC',key,enc.encode('cloudflare-admin-v1'))));
}
export async function authorized(request, secret) {
  if (!secret) return false;
  const actual = request.headers.get('Authorization') || '';
  const expected = 'Bearer ' + await adminToken(secret);
  const a = new Uint8Array(await crypto.subtle.digest('SHA-256',enc.encode(actual)));
  const b = new Uint8Array(await crypto.subtle.digest('SHA-256',enc.encode(expected)));
  let difference = 0;
  for (let i=0;i<a.length;i++) difference |= a[i]^b[i];
  return difference === 0;
}
