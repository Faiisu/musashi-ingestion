"""Offline language-switch rendering checks; no browser or service required."""

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE_CHECK = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const root = process.cwd() + '/src/musashi_ingestion/web/';
const document = {body:{querySelectorAll:()=>[]},documentElement:{lang:'en'},createTreeWalker:()=>({nextNode:()=>null}),querySelectorAll:()=>[],addEventListener:()=>{}};
const context = {window:{dispatchEvent:()=>{}},document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem:()=>null,setItem:(key,value)=>{context.saved=value;}},Event:class {},Intl,Date};
vm.createContext(context);
for (const name of ['translations_th.js','i18n.js','page_config.js','page_machines.js','page_destinations.js','page_records.js','page_overview.js']) vm.runInContext(fs.readFileSync(root+name,'utf8'),context);
const i=context.window.MusashiI18n;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const helpers={esc,number:v=>String(v),date:()=> '2026-10-06',ago:()=>i.t('No data yet'),workersActive:s=>!!s.status.running,machineStatus:()=>({}),destinationStatus:()=>({}),machineState:()=> 'stopped',destinationState:()=> 'stopped',statusBadge:()=>i.t('Stopped'),pageHeading:(k,t,d,a)=>`<h1>${t}</h1><p>${d}</p>${a||''}`,emptyPanel:(t,d)=>`<strong>${t}</strong><p>${d}</p>`,metric:(l,v,u,f)=>`<p>${l}</p><p>${v} ${u}</p><p>${f}</p>`};
const state={config:{version:1,revision:2,auto_start:false,machines:[{id:'Machines',model:'IV',host:'192.168.1.20',channel_count:2,recipe_count:1}],destinations:[{id:'Overview',kind:'mqtt',host:'broker.local',topic:'Configuration',secret_ref:'********'}]},status:{running:false,spool:{}},records:[],scans:[],spoolSamples:[],machineFilter:'all',machineQuery:'',destinationFilter:'all',destinationQuery:''};
for (const lang of ['en','th','en']) {
 i.setLanguage(lang);
 assert.equal(i.language,lang); assert.equal(i.t('Configuration'),lang==='th'?'การตั้งค่า':'Configuration');
 for (const [name,page] of Object.entries(context.window.MusashiPages)) {
  const output=(typeof page==='function'?page:page.render)({state,helpers});
  assert(!output.includes('undefined'),'undefined output on '+name);
  if(name==='config') {
   assert(!output.includes('data-action='), 'reference must have no mutations');
   assert(!output.includes('broker.local'), 'reference must not contain live settings');
   assert(!output.includes('>Machines</h3>'), 'reference must not contain machine instances');
   for (const section of ['system','machines','iii','iv','destinations','mqtt','postgres','influxdb','environment','secrets','examples']) assert(output.includes(`id="config-${section}"`));
   for (const field of ['version','revision','auto_start','machines','destinations','id','model','simulated','poll_interval_seconds','inventory_interval_seconds','host','port','channel_count','recipe_count','kind','topic','tls','ca_file','secret_ref','url','org','bucket','max_payload_bytes','connect_timeout_seconds','timeout_ms','verify_ssl','MUSASHI_DATA_DIR','MUSASHI_BIND','MUSASHI_PORT','MUSASHI_PUBLIC_ORIGIN','MUSASHI_ALLOWED_ORIGINS','OPERATOR_USERNAME','OPERATOR_PASSWORD']) assert(output.includes(`<code>${field}</code>`), field);
   assert.equal(output,page({state:{config:null,status:null},helpers}), 'reference must work without live config');
   assert(output.includes(lang==='th' ? 'คู่มือการตั้งค่า' : 'Configuration reference'));
  }

 }
 const output=i.msg`<p>${esc('Machines')} seconds ago</p><p>${esc('Overview')}</p>`;
 assert.equal(output,lang==='th'?'<p>Machines วินาทีที่แล้ว</p><p>Overview</p>':'<p>Machines seconds ago</p><p>Overview</p>');
}
assert.equal(context.saved,'en');
i.setLanguage('th');
const reload = {...context, window:{dispatchEvent:()=>{}}, localStorage:{getItem:()=>context.saved,setItem:()=>{}}};
vm.createContext(reload);
for (const name of ['translations_th.js','i18n.js']) vm.runInContext(fs.readFileSync(root+name,'utf8'),reload);
assert.equal(reload.window.MusashiI18n.language,'th');
const blocked = {...context, window:{dispatchEvent:()=>{}}, localStorage:{getItem:()=>{throw Error('blocked')},setItem:()=>{throw Error('blocked')}}};
vm.createContext(blocked);
for (const name of ['translations_th.js','i18n.js']) vm.runInContext(fs.readFileSync(root+name,'utf8'),blocked);
assert.equal(blocked.window.MusashiI18n.language,'en');
blocked.window.MusashiI18n.setLanguage('th');
assert.equal(blocked.window.MusashiI18n.language,'th');
"""


class WebLanguageTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required for UI rendering checks")
    def test_localization_preserves_data_actions_and_browser_preference(self):
        result = subprocess.run(
            [shutil.which("node"), "-e", NODE_CHECK],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
