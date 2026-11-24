"""Fetch the official Docker image through the existing Windows loopback proxy.
Creates a docker-load archive; validates every registry blob digest.
"""
import urllib.request,json,hashlib,gzip,shutil,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];dest=root/'data/onlyoffice-image';dest.mkdir(exist_ok=True)
repo='onlyoffice/documentserver';tag='9.3.1'
op=urllib.request.build_opener(urllib.request.ProxyHandler({'https':'http://127.0.0.1:7890'}))
token=json.load(op.open('https://auth.docker.io/token?service=registry.docker.io&scope=repository:'+repo+':pull',timeout=30))['token']
def request(path):return urllib.request.Request('https://registry-1.docker.io/v2/'+repo+'/'+path,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json'})
manifest=json.load(op.open(request('manifests/'+tag),timeout=60))
if 'manifests' in manifest:
 digest=next(x['digest'] for x in manifest['manifests'] if x.get('platform',{}).get('architecture')=='amd64' and x.get('platform',{}).get('os')=='linux')
 manifest=json.load(op.open(request('manifests/'+digest),timeout=60))
layers=[]
for item in [manifest['config']]+manifest['layers']:
 digest=item['digest'];name=digest.split(':')[1];path=dest/name
 if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=name:
  with op.open(request('blobs/'+digest),timeout=180) as r,path.open('wb') as f:shutil.copyfileobj(r,f)
  if hashlib.sha256(path.read_bytes()).hexdigest()!=name:raise ValueError('Blob digest mismatch')
 if item is not manifest['config']:
  uncompressed=dest/(name+'.tar')
  if not uncompressed.exists():
   with gzip.open(path,'rb') as src,uncompressed.open('wb') as dst:shutil.copyfileobj(src,dst)
  layers.append(uncompressed.name)
 print('Verified',len(layers),'of',len(manifest['layers']),flush=True)
record=[{'Config':manifest['config']['digest'].split(':')[1],'RepoTags':[repo+':'+tag],'Layers':layers}]
(dest/'manifest.json').write_text(json.dumps(record))
with tarfile.open(dest/'onlyoffice.tar','w') as tar:
 for name in ['manifest.json',record[0]['Config']]+layers:tar.add(dest/name,arcname=name)
print('Image archive ready',flush=True)
