#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 - <<'PY'
import json,pathlib,secrets
p=pathlib.Path('config/onlyoffice.local.json')
if not p.exists():p.write_text(json.dumps({'browserUrl':'http://localhost:8080','storageUrl':'http://127.0.0.1:8766','callbackFetchUrl':'http://127.0.0.1:80','secret':secrets.token_urlsafe(40)}))
c=json.loads(p.read_text());pathlib.Path('data/onlyoffice.env').write_text('JWT_ENABLED=true\nJWT_SECRET='+c['secret']+'\nALLOW_PRIVATE_IP_ADDRESS=true\n')
PY
if ! docker image inspect onlyoffice/documentserver:9.3.1 >/dev/null 2>&1; then
 if [ -f data/onlyoffice-image/onlyoffice.tar ]; then docker load -i data/onlyoffice-image/onlyoffice.tar; else docker pull onlyoffice/documentserver:9.3.1; fi
fi
if docker container inspect zhixi-onlyoffice >/dev/null 2>&1; then docker start zhixi-onlyoffice; else
 mkdir -p data/editor
 docker run -d --name zhixi-onlyoffice -p 127.0.0.1:8080:80 --env-file data/onlyoffice.env --shm-size=1g -v "$PWD/onlyoffice_service.py:/opt/zhixi/onlyoffice_service.py:ro" -v "$PWD/review_document.py:/opt/zhixi/review_document.py:ro" -v "$PWD/config/onlyoffice.local.json:/opt/zhixi/config/onlyoffice.local.json:ro" -v "$PWD/data/editor:/opt/zhixi/data/editor" onlyoffice/documentserver:9.3.1
fi
docker exec -d -w /opt/zhixi zhixi-onlyoffice python3 onlyoffice_service.py
echo 'ONLYOFFICE starting: http://localhost:8080/healthcheck'
