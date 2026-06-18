# Design — Anexos no S3 via presigned URLs (bucket privado)

Data: 2026-06-18
App: `tickets` + `core` (backend Django + DRF)

## Objetivo

Mover o armazenamento dos anexos (hoje só uma URL informada pelo front) para o
**Amazon S3**, usando **presigned URLs**: o arquivo vai **direto do navegador para o
S3**, sem passar pelo Django. O bucket é **privado** — a URL de leitura é gerada e
assinada na hora (expira), nunca um link permanente.

Escopo imediato: anexos de **comentário** (`TicketCommentAttachment`). O serviço S3
é escrito de forma reutilizável para o `TicketAttachment` (nível ticket) adotar depois.

## Fluxo (3 passos)

```
1. front → POST /tickets/uploads/presign  {filename, content_type}
          ← {key, upload_url, expires_in}
2. front → PUT <upload_url>  (corpo = bytes do arquivo)  → vai direto pro S3
3. front → POST /tickets/comments  {ticket, body, attachments_input: [{key, name}]}
```

Na **leitura** do comentário, cada anexo retorna uma **presigned GET** fresca
(`url`), gerada no momento da serialização e com expiração curta.

## Decisões tomadas

- **Presigned URL** (não proxy pelo backend): o arquivo não trafega pelo servidor.
- **Bucket privado**: leitura exige presigned GET assinada na hora.
- **Presigned PUT** para upload (simples, 1 arquivo por chave).
- Guardar a **`key`** do objeto no banco (não a URL). O **nome original** do arquivo
  fica em `name` (para exibição amigável — a `key` tem uuid).

## Fora de escopo (YAGNI)

- Migrar `TicketAttachment` (nível ticket) agora — serviço fica pronto p/ adotar.
- Limite de tamanho imposto pelo servidor (presigned PUT não força tamanho; evoluir
  para presigned POST com policy se necessário).
- Antivírus / validação de conteúdo do arquivo.

## 1. Configuração

### `.env` (novas variáveis)
```
AWS_STORAGE_BUCKET_NAME=help-desk-anexos
AWS_S3_REGION_NAME=sa-east-1
AWS_ACCESS_KEY_ID=...        # em dev; em prod, preferir IAM role e deixar vazio
AWS_SECRET_ACCESS_KEY=...
AWS_S3_PRESIGN_EXPIRE=3600   # segundos (opcional)
```

### `settings.py` (ler via django-environ, com defaults)
```python
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default='sa-east-1')
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY', default='')
AWS_S3_PRESIGN_EXPIRE = env.int('AWS_S3_PRESIGN_EXPIRE', default=3600)
```

## 2. Serviço S3 — `core/s3.py`

Wrapper fino sobre boto3, transversal (serve tickets/comentários e futuros).

```python
import uuid
from pathlib import PurePosixPath

import boto3
from botocore.config import Config
from django.conf import settings


def _client():
    # Cliente boto3. Se as chaves não estiverem no settings, o boto3 cai no
    # provedor padrão (IAM role / ~/.aws), bom para produção.
    kwargs = {'region_name': settings.AWS_S3_REGION_NAME,
              'config': Config(signature_version='s3v4')}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
        kwargs['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client('s3', **kwargs)


def build_key(prefix, filename):
    # Chave única e segura: prefix/uuid/nome-saneado. Mantém a extensão.
    safe = PurePosixPath(filename).name.replace('/', '_')
    return f'{prefix}/{uuid.uuid4()}/{safe}'


def generate_upload_url(key, content_type):
    # Presigned PUT: o navegador sobe o arquivo direto pro S3.
    return _client().generate_presigned_url(
        'put_object',
        Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': key, 'ContentType': content_type},
        ExpiresIn=settings.AWS_S3_PRESIGN_EXPIRE,
    )


def generate_download_url(key):
    # Presigned GET: link temporário para ler um objeto privado.
    return _client().generate_presigned_url(
        'get_object',
        Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': key},
        ExpiresIn=settings.AWS_S3_PRESIGN_EXPIRE,
    )
```

Observação: `signature_version='s3v4'` é necessário para presign correto em regiões
novas (ex.: `sa-east-1`).

## 3. Model — `tickets/models.py`

`TicketCommentAttachment` passa a guardar a **chave** do objeto no S3 em vez da URL:

```python
class TicketCommentAttachment(models.Model):
    comment = models.ForeignKey(TicketComment, on_delete=models.CASCADE, related_name='attachments')
    key = models.CharField(max_length=600)      # chave do objeto no S3 (privado)
    name = models.CharField(max_length=255)      # nome ORIGINAL do arquivo (exibição)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'db_ticket_comment_attachment'
        verbose_name = 'Ticket Comment Attachment'
        verbose_name_plural = 'Ticket Comment Attachments'

    def __str__(self):
        return self.name
```

(O objeto S3 em si não é apagado ao deletar o comentário neste escopo — só a linha.
Limpeza no bucket fica para depois, se necessário.)

## 4. Endpoint de presign — `tickets/views.py` + `tickets/urls.py`

`APIView` dedicada (não é recurso de model), protegida pelo `IsAuthenticated` global.

```python
class AttachmentPresignView(APIView):
    def post(self, request):
        filename = request.data.get('filename')
        content_type = request.data.get('content_type', 'application/octet-stream')
        if not filename:
            return Response({'detail': 'filename é obrigatório.'}, status=400)
        key = build_key('tickets/comments', filename)
        return Response({
            'key': key,
            'upload_url': generate_upload_url(key, content_type),
            'expires_in': settings.AWS_S3_PRESIGN_EXPIRE,
        })
```

Em `tickets/urls.py`, adicionar fora do router:
```python
urlpatterns = [
    path('uploads/presign', AttachmentPresignView.as_view(), name='attachment-presign'),
    *router.urls,
]
```
A rota literal `uploads/presign` vem **antes** das do router (mesmo cuidado das rotas
nomeadas: não pode ser capturada como id de ticket).

## 5. Serializer — `tickets/serializer.py`

```python
class TicketCommentAttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()   # presigned GET, gerada na leitura

    class Meta:
        model = TicketCommentAttachment
        fields = ["id", "key", "name", "url", "uploaded_at"]
        read_only_fields = ["url", "uploaded_at"]
        extra_kwargs = {"key": {"write_only": True}}  # key entra na escrita, sai só via url

    def get_url(self, obj):
        return generate_download_url(obj.key)
```

- **Escrita**: `attachments_input` recebe `[{key, name}]` (a `key` que o front obteve
  no presign + subiu). O `_sync_attachments` salva `key` e `name`.
- **Leitura**: cada anexo retorna `{id, name, url (assinada, temporária), uploaded_at}`.

## 6. Setup na AWS (fora do código — passo a passo para o usuário)

1. Criar bucket **privado** (Block Public Access **ligado**).
2. Configurar **CORS** do bucket liberando `PUT`/`GET` do domínio do front:
   ```json
   [{"AllowedMethods":["PUT","GET"],
     "AllowedOrigins":["https://SEU-FRONT"],
     "AllowedHeaders":["*"],
     "ExposeHeaders":["ETag"]}]
   ```
3. Usuário/role IAM com política mínima: `s3:PutObject` + `s3:GetObject`
   em `arn:aws:s3:::SEU-BUCKET/*`.
4. Preencher as variáveis no `.env`.

## 7. Testes (`tickets/tests.py`)

Como os testes não devem bater na AWS de verdade, mockar `core.s3`:
1. `POST /tickets/uploads/presign` sem `filename` → 400.
2. `POST /tickets/uploads/presign` com filename → 200 com `key`, `upload_url`,
   `expires_in` (com `generate_upload_url` mockado).
3. Criar comentário com `attachments_input=[{key, name}]` → anexos persistidos com
   a `key` e o `name` corretos.
4. Ler o comentário → cada anexo traz `url` (vindo de `generate_download_url`
   mockado) e **não** expõe a `key`.
5. `build_key` gera chaves únicas e preserva a extensão/nome saneado.

## Ordem de implementação

1. `core/s3.py` (serviço)
2. `settings.py` + exemplo no `.env`
3. Endpoint `AttachmentPresignView` + rota
4. Ajuste do model `TicketCommentAttachment` (`url` → `key`) + serializer
5. Reseta do banco (migration nova entra no 0001) + testes
