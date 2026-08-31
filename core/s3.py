"""Serviço fino sobre o boto3 para anexos no S3 (bucket privado, presigned URLs).

Transversal — hoje serve os anexos de comentário (tickets), e pode ser reusado
por outros recursos. O arquivo nunca passa pelo Django: o front sobe direto pro
S3 com uma presigned PUT, e a leitura usa presigned GET gerada na hora.
"""

import uuid
from pathlib import PurePosixPath

import boto3
from botocore.config import Config
from django.conf import settings


def _client():
    # Cliente boto3. Sem chaves no settings, o boto3 cai no provedor padrão
    # (IAM role / ~/.aws) — bom para produção. s3v4 é necessário p/ presign
    # correto em regiões novas (ex.: sa-east-1).
    kwargs = {
        'region_name': settings.AWS_S3_REGION_NAME,
        # Endpoint regional explícito: sem isso o boto assina com o host global
        # (s3.amazonaws.com) e o S3 devolve 307 redirect p/ a região — o que
        # quebra o PUT do navegador por CORS. Ver core/s3.py.
        'endpoint_url': f'https://s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com',
        'config': Config(signature_version='s3v4'),
    }
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kwargs['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
        kwargs['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY
    return boto3.client('s3', **kwargs)


def build_key(prefix, filename):
    # Chave única e segura: prefix/uuid/nome-saneado. Preserva nome/extensão.
    safe = PurePosixPath(filename).name.replace('/', '_')
    return f'{prefix}/{uuid.uuid4()}/{safe}'


def upload_fileobj(fileobj, prefix, content_type=None):
    # Upload feito PELO backend: recebe o arquivo do request (multipart) e sobe
    # pro S3 (bucket privado), devolvendo a key. A leitura continua via presigned
    # GET (generate_download_url). Sem presign de PUT / sem CORS no navegador.
    key = build_key(prefix, getattr(fileobj, 'name', None) or 'file')
    extra = {'ContentType': content_type} if content_type else None
    _client().upload_fileobj(
        fileobj,
        settings.AWS_STORAGE_BUCKET_NAME,
        key,
        ExtraArgs=extra,
    )
    return key


def get_object_stream(key):
    # Lê o objeto do S3 (bucket privado) usando as credenciais do servidor.
    # Devolve o response do boto3: ['Body'] é um stream, e ainda traz
    # ContentType / ContentLength. Usado pelo proxy de download (sem expor URL S3).
    return _client().get_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
    )
