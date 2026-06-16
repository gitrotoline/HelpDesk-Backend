---
name: reseta
description: Recria o banco do help-desk backend do zero. Use quando o usuário disser "reseta" (ou pedir para resetar/recriar o banco) — apaga as migrations dos apps do projeto, dropa e recria o banco `helpdesk`, refaz e aplica as migrations, e roda os seeds.
---

# Reseta do banco — help-desk backend

Rodar **de `backend/`** com o virtualenv ativo. Credenciais do banco vêm do `.env`
(`DB_NAME=helpdesk`, `DB_USER=postgres`, `DB_PASSWORD=12345`, `localhost:5432`).
Referência completa: `backend/COMANDOS.md`, seção "reseta".

Executar **nesta ordem**:

## 1. Apagar as migrations dos apps (mantendo `__init__.py`)

⚠️ **SÓ os apps do projeto — NUNCA recursar a partir de `backend/`**, senão apaga as
migrations dos pacotes em `.venv\Lib\site-packages\` (Django, DRF, simplejwt) e quebra
tudo (`ModuleNotFoundError: django.db.migrations.migration`).

PowerShell:
```powershell
$apps = 'core','tickets','machines','enterprises','sector','users','authentication'
foreach ($a in $apps) {
  Get-ChildItem "$a\migrations" -Filter *.py -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne '__init__.py' } | Remove-Item -Force
  Remove-Item "$a\migrations\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
}
```

## 2. Dropar e recriar o banco `helpdesk`

`psql` não está no PATH; usar psycopg2. PowerShell estraga aspas em `python -c`, então
escrever um arquivo `.py` temporário e rodar (depois apagar):

```python
# _reset_db.py
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

c = psycopg2.connect(dbname='postgres', user='postgres', password='12345',
                     host='localhost', port='5432')
c.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = c.cursor()
cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname='helpdesk' AND pid<>pg_backend_pid();")
cur.execute('DROP DATABASE IF EXISTS helpdesk;')
cur.execute('CREATE DATABASE helpdesk;')
print('helpdesk recriado')
```
```powershell
python _reset_db.py; Remove-Item _reset_db.py -Force
```

## 3-4. Refazer e aplicar migrations

```powershell
python manage.py makemigrations
python manage.py migrate
```

## 5. Seeds

```powershell
python manage.py ticket_refs       # status, prioridades e tipos de ticket
python manage.py country           # países
python manage.py state_and_city    # estados e cidades
```

## Confirmar

`python manage.py check` deve passar limpo.
