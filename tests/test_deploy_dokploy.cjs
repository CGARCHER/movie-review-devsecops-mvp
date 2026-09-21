const assert = require('node:assert/strict');
const deploy = require('../scripts/deploy_dokploy.cjs');
Object.assign(process.env, {DOKPLOY_URL:'https://example.test', DOKPLOY_API_KEY:'test-only', DOKPLOY_COMPOSE_ID:'compose-test', GITHUB_RUN_ATTEMPT:'1'});
const context={sha:'a'.repeat(40), runId:123, repo:{owner:'owner',repo:'repo'}};
const core={info(){}};
async function scenario({config={},status='done',existingTag=false,wrongTag=false,oldDone=false,requestFails=false,wrongCommit=false,duplicate=false,runningFirst=false}={}) {
  const calls=[];
  let polls=0;
  const github={rest:{git:{
    async createRef(args){ calls.push('tag'); assert.equal(args.sha,context.sha); if(existingTag) throw Object.assign(new Error(),{status:422}); },
    async getRef(){return {data:{object:{type:'commit',sha:wrongTag?'b'.repeat(40):context.sha}}};}
  }}};
  global.fetch=async (url,options)=>{
    calls.push(url.pathname);
    let result;
    if(url.pathname==='/api/compose.one')result={sourceType:'github',owner:'owner',repository:'repo',autoDeploy:false,command:'',...config};
    else if(url.pathname==='/api/deployment.allByCompose'){
      polls++;
      // Formato observado en Dokploy: reemplaza ambos textos con datos del commit.
      result=polls===1?[{deploymentId:'old',description:'Commit: '+context.sha,status:'done'}]:[{deploymentId:oldDone?'old':'new',title:'Mensaje del commit de GitHub',description:'Commit: '+(wrongCommit?'b'.repeat(40):context.sha),status:runningFirst&&polls===2?'running':status}];
      if(duplicate&&polls>1)result.push({...result[0],deploymentId:'another'});
    } else if(url.pathname==='/api/compose.update'){
      const body=JSON.parse(options.body);assert.equal(body.branch,'deploy-'+context.sha);assert.equal(body.composePath,'./compose.main.yml');result={};
    } else if(url.pathname==='/api/compose.deploy'){assert.equal(JSON.parse(options.body).description,'Commit: '+context.sha);result={success:true};}
    else throw new Error('Unexpected route');
    return {ok:!requestFails,status:requestFails?403:200,json:async()=>result};
  };
  const realTimeout=global.setTimeout;
  global.setTimeout=(callback)=>{callback();};
  try {await deploy({github,context,core});return calls;} finally{global.setTimeout=realTimeout;}
}
(async()=>{
  const calls=await scenario();
  assert(calls.indexOf('tag')<calls.indexOf('/api/compose.update'));
  assert(calls.indexOf('/api/compose.update')<calls.indexOf('/api/compose.deploy'));
  await scenario({existingTag:true});
  await assert.rejects(scenario({existingTag:true,wrongTag:true}),/etiqueta/);
  await assert.rejects(scenario({config:{autoDeploy:true}}),/Autodeploy/);
  await assert.rejects(scenario({config:{repository:'other'}}),/repositorio/);
  await assert.rejects(scenario({status:'error'}),/fallado/);
  await assert.rejects(scenario({oldDone:true}),/diez minutos/);
  await assert.rejects(scenario({requestFails:true}),/HTTP 403/);
  await assert.rejects(scenario({wrongCommit:true}),/diez minutos/);
  await assert.rejects(scenario({duplicate:true}),/varios despliegues/);
  await scenario({runningFirst:true});
  console.log('11 escenarios de despliegue simulados: correctos. No se han realizado peticiones reales.');
})().catch(error=>{console.error(error);process.exitCode=1;});

