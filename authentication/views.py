import json

import requests
from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def login_view(request):
    if request.method != 'POST':
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    data = json.loads(request.body or '{}')

    try:
        r = requests.post(
            f'{settings.AUTH_SERVER_URL}auth/login/',
            json={
                'username': data.get('username', ''),
                'password': data.get('password', ''),
            },
            timeout=5,
        )
    except requests.RequestException:
        return JsonResponse(
            {"detail": 'Não foi possível contatar o servidor de autenticação.'},
            status=502,
        )

    if r.status_code == 200:
        return JsonResponse(r.json())

    return JsonResponse({"detail": 'Credenciais inválidas.'}, status=401)

def me_view(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse({"detail": "Não autenticado."}, status=401)

    return JsonResponse({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "cpf": user.cpf,
        "sap_code": user.sap_code,
        "email_verified": user.email_verified,
        "phone": user.phone,
        "phone_verified": user.phone_verified,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "department": {"id": user.departamento.id, "name": user.departamento.nome} if user.departamento else None,
        "sector": {"id": user.setor.id, "name": user.setor.nome} if user.setor else None,
        "schedule": {"id": user.escala.id, "name": user.escala.nome} if user.escala else None,
        "groups": user.groups.values_list("name", flat=True),
        "permissions": user.permissions,
    })


@csrf_exempt
def refresh_view(request):
    if request.method != 'POST':
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    data = json.loads(request.body or '{}')
    refresh = data.get('refresh')
    if not refresh:
        return JsonResponse({"detail": "Refresh token ausente."}, status=400)

    try:
        r = requests.post(
            f'{settings.AUTH_SERVER_URL}auth/refresh/',
            json={'refresh': refresh},
            timeout=5,
        )
    except requests.RequestException:
        return JsonResponse(
            {"detail": 'Não foi possível contatar o servidor de autenticação.'},
            status=502,
        )

    if r.status_code == 200:
        return JsonResponse(r.json())

    return JsonResponse({"detail": 'Refresh token inválido ou expirado.'}, status=401)


@csrf_exempt
def logout_view(request):
      if request.method != 'POST':
          return JsonResponse({"detail": "Method not allowed"}, status=405)

      data = json.loads(request.body or '{}')
      access = data.get('access')
      refresh = data.get('refresh')

      if refresh:
          try:
              requests.post(
                  f'{settings.AUTH_SERVER_URL}auth/logout/',
                  json={'refresh': refresh},
                  headers={'Authorization': f'Bearer {access}'} if access else {},
                  timeout=5,
              )
          except requests.RequestException:
              pass

      return JsonResponse({"detail": "ok"})


def signup(request):
    return JsonResponse({"mensagem": "Criar conta"})